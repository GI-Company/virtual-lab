import time
import json
import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QGroupBox, QComboBox, QInputDialog, QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
import pyqtgraph as pg
import numpy as np

from virtual_lab.instruments.camera import CameraFrame, CameraStreamKey
from virtual_lab.instruments.optics import SpatialCalibration, OpticalSetup, RegionOfInterest, AnalysisRun, generate_id, hash_bytes
from virtual_lab.instruments.analysis import jpeg_to_numpy, calculate_pixel_statistics, threshold_connected_components, calculate_focus_metric
from virtual_lab.core.ledger import Actor
from virtual_lab.gui.instruments.control_panel import ControlPanel

class OpticalPanel(QWidget):
    def __init__(self, workspace, gateway, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.gateway = gateway
        
        self.current_frame: CameraFrame = None
        self.frozen_frame: CameraFrame = None
        self.frozen_image_array: np.ndarray = None
        
        self.current_setup = OpticalSetup(
            setup_id="OPT-DEFAULT",
            device_id="UNKNOWN",
            camera_stream_key=None
        )
        self.current_calibration: SpatialCalibration = None
        
        self.is_calibrating = False
        self.calibration_roi = None
        self.analysis_rois = []
        
        self._init_ui()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        
        # Left Panel (Controls)
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        self.left_panel.setMaximumWidth(350)
        
        # Header Info
        self.group_info = QGroupBox("OPTICAL STATUS")
        info_layout = QVBoxLayout(self.group_info)
        
        self.lbl_camera = QLabel("Camera: None")
        self.lbl_mode = QLabel("Mode: MICROSCOPE")
        self.lbl_setup = QLabel(f"Optical Setup: {self.current_setup.setup_id}")
        self.lbl_calib = QLabel("Calibration: UNSCALED IMAGE — PIXEL UNITS ONLY")
        self.lbl_calib.setStyleSheet("color: #f59e0b; font-weight: bold;")
        
        info_layout.addWidget(self.lbl_camera)
        info_layout.addWidget(self.lbl_mode)
        info_layout.addWidget(self.lbl_setup)
        info_layout.addWidget(self.lbl_calib)
        left_layout.addWidget(self.group_info)
        
        # Focus Assist Metric
        self.lbl_focus_assist = QLabel("FOCUS ASSIST — DERIVED\nMethod: TENENGRAD\nScore: --")
        self.lbl_focus_assist.setStyleSheet("font-family: monospace; color: #38bdf8;")
        left_layout.addWidget(self.lbl_focus_assist)
        
        # Control Panel Widget
        self.control_panel = ControlPanel(self.gateway)
        left_layout.addWidget(self.control_panel)
        
        main_layout.addWidget(self.left_panel)
        
        # Right Panel (Image & Actions)
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        
        # Image View using pyqtgraph
        self.image_view = pg.ImageView()
        # Disable the default ROI and norm buttons of ImageView to keep it clean
        self.image_view.ui.roiBtn.hide()
        self.image_view.ui.menuBtn.hide()
        self.image_view.ui.histogram.hide()
        right_layout.addWidget(self.image_view)
        
        # Controls
        controls = QHBoxLayout()
        self.btn_freeze = QPushButton("Freeze for Analysis")
        self.btn_freeze.clicked.connect(self._toggle_freeze)
        controls.addWidget(self.btn_freeze)
        
        self.btn_calibrate = QPushButton("Calibrate Scale")
        self.btn_calibrate.clicked.connect(self._start_calibration)
        controls.addWidget(self.btn_calibrate)
        
        self.btn_threshold = QPushButton("Threshold Analysis")
        self.btn_threshold.clicked.connect(self._run_threshold_analysis)
        self.btn_threshold.setEnabled(False)
        controls.addWidget(self.btn_threshold)
        
        right_layout.addLayout(controls)
        
        self.lbl_stats = QLabel("Scientific State: MEASURED IMAGE")
        self.lbl_stats.setStyleSheet("font-family: monospace;")
        right_layout.addWidget(self.lbl_stats)
        
        main_layout.addWidget(self.right_panel)

    def process_live_frame(self, frame: CameraFrame):
        if self.frozen_frame is not None:
            return # Ignore live frames while frozen
            
        self.current_frame = frame
        self._update_setup_from_frame(frame)
        
        # Render the preview frame (transpose required for pyqtgraph display (W, H, C) vs (H, W, C) numpy)
        # Note: We must NOT mutate the scientific array!
        try:
            arr = jpeg_to_numpy(frame.jpeg_bytes)
            
            # Calculate focus metric (Tenengrad)
            focus_score = calculate_focus_metric(arr, method="TENENGRAD")
            self.lbl_focus_assist.setText(f"FOCUS ASSIST — DERIVED\nMethod: TENENGRAD\nScore: {focus_score:.2f}")
            
            # pyqtgraph expects (width, height, color)
            disp_arr = arr.transpose((1, 0, 2))
            self.image_view.setImage(disp_arr, autoRange=False, autoLevels=False)
            self.lbl_camera.setText(f"Camera: {frame.camera_id} (Log: {frame.logical_camera_id}, Phys: {frame.physical_camera_id})")
            
        except Exception as e:
            print(f"Error rendering preview: {e}")

    def _update_setup_from_frame(self, frame: CameraFrame):
        key = frame.stream_key
        if self.current_setup.camera_stream_key != key:
            self.current_setup.camera_stream_key = key
            self.current_setup.device_id = frame.device_id
            self.current_setup.resolution = f"{frame.width}x{frame.height}"
            
            # Invalidate calibration on setup change
            self.current_calibration = None
            self.lbl_calib.setText("Calibration: UNSCALED IMAGE — PIXEL UNITS ONLY")
            self.lbl_calib.setStyleSheet("color: #f59e0b; font-weight: bold;")

    def _toggle_freeze(self):
        if self.frozen_frame is None:
            if not self.current_frame:
                return
            # Freeze
            self.frozen_frame = self.current_frame
            self.frozen_image_array = jpeg_to_numpy(self.frozen_frame.jpeg_bytes)
            
            self.btn_freeze.setText("Unfreeze (Resume Live)")
            self.btn_freeze.setStyleSheet("background-color: #3b82f6; color: white;")
            self.btn_calibrate.setEnabled(True)
            self.btn_threshold.setEnabled(True)
            
            self.lbl_stats.setText("Scientific State: OPTICAL ANALYSIS SNAPSHOT (FROZEN)")
        else:
            # Unfreeze
            self.frozen_frame = None
            self.frozen_image_array = None
            if self.calibration_roi:
                self.image_view.getView().removeItem(self.calibration_roi)
                self.calibration_roi = None
            for roi in self.analysis_rois:
                self.image_view.getView().removeItem(roi)
            self.analysis_rois.clear()
            self.is_calibrating = False
            
            self.btn_freeze.setText("Freeze for Analysis")
            self.btn_freeze.setStyleSheet("")
            self.btn_threshold.setEnabled(False)
            self.lbl_stats.setText("Scientific State: MEASURED IMAGE")

    def _start_calibration(self):
        if not self.frozen_frame:
            return
            
        if not self.is_calibrating:
            self.is_calibrating = True
            self.btn_calibrate.setText("Confirm Calibration")
            
            # Add a line ROI for the user to measure
            # Coordinates in pyqtgraph are (x, y) which maps to (width, height)
            w = self.frozen_frame.width
            h = self.frozen_frame.height
            self.calibration_roi = pg.LineSegmentROI([[w/4, h/2], [w*3/4, h/2]], pen='y')
            self.image_view.getView().addItem(self.calibration_roi)
        else:
            # Confirm
            pts = self.calibration_roi.getSceneHandlePositions()
            if len(pts) >= 2:
                # Get the handle positions in the item's coordinate system
                p1 = self.calibration_roi.mapSceneToParent(pts[0][1])
                p2 = self.calibration_roi.mapSceneToParent(pts[1][1])
                
                # pyqtgraph x, y maps to numpy x (width), y (height)
                # Let's keep source pixel coordinates: (x, y)
                dx = p2.x() - p1.x()
                dy = p2.y() - p1.y()
                pixel_dist = np.sqrt(dx**2 + dy**2)
                
                distance, ok = QInputDialog.getDouble(self, "Spatial Calibration", 
                    f"Pixel distance: {pixel_dist:.2f} px\nEnter known reference distance:", 
                    1.0, 0.001, 10000.0, 3)
                    
                if ok:
                    unit, ok2 = QInputDialog.getText(self, "Spatial Calibration", "Enter unit (e.g., mm, um):", text="um")
                    if ok2:
                        # Normalize to um for standard storage
                        dist_um = distance
                        if unit == "mm": dist_um = distance * 1000.0
                        
                        mpp = dist_um / pixel_dist
                        
                        calib_id = generate_id("CAL")
                        self.current_calibration = SpatialCalibration(
                            calibration_id=calib_id,
                            device_id=self.frozen_frame.device_id,
                            camera_stream_key=self.frozen_frame.stream_key,
                            optical_setup_id=self.current_setup.setup_id,
                            source_frame_hash=hash_bytes(self.frozen_frame.jpeg_bytes),
                            resolution_width=self.frozen_frame.width,
                            resolution_height=self.frozen_frame.height,
                            orientation=0, # Assuming 0 for now
                            reference_distance=distance,
                            reference_unit=unit,
                            reference_distance_um=dist_um,
                            pixel_line_start=(p1.x(), p1.y()),
                            pixel_line_end=(p2.x(), p2.y()),
                            pixel_distance=pixel_dist,
                            microns_per_pixel_x=mpp,
                            microns_per_pixel_y=mpp,
                            isotropic_scale_assumed=True,
                            calibration_method="LINE_SEGMENT_MANUAL",
                            created_utc=int(time.time() * 1000),
                            operator="VirtualLab User"
                        )
                        
                        self.lbl_calib.setText(f"Calibration: {mpp:.4f} µm/px | VERIFIED")
                        self.lbl_calib.setStyleSheet("color: #22c55e; font-weight: bold;")
                        
                        self.workspace.ledger.append(
                            event_id=generate_id("EVT"),
                            actor=Actor(type="SYSTEM", id="virtual_lab"),
                            event_type="OPTICAL_SPATIAL_CALIBRATION_CREATED",
                            payload={
                                "calibration_id": calib_id,
                                "optical_setup_id": self.current_setup.setup_id,
                                "source_frame_hash": self.current_calibration.source_frame_hash,
                                "reference_distance": distance,
                                "pixel_distance": pixel_dist,
                                "microns_per_pixel": mpp
                            }
                        )
            
            self.image_view.getView().removeItem(self.calibration_roi)
            self.calibration_roi = None
            self.is_calibrating = False
            self.btn_calibrate.setText("Calibrate Scale")

    def _run_threshold_analysis(self):
        if not self.frozen_frame or self.frozen_image_array is None:
            return
            
        threshold, ok = QInputDialog.getInt(self, "Threshold Analysis", 
            "Enter grayscale threshold (0-255):", 128, 0, 255)
            
        if ok:
            # We run analysis on the original un-transposed array (H, W, 3)
            num_features, labeled = threshold_connected_components(self.frozen_image_array, threshold)
            stats = calculate_pixel_statistics(self.frozen_image_array)
            
            run_id = generate_id("ANL")
            
            # Format results
            res_text = f"Scientific State: DERIVED ANALYSIS\n"
            res_text += f"Run: {run_id}\n"
            res_text += f"Threshold-derived connected components: {num_features}\n"
            res_text += f"PIXEL INTENSITY Mean: {stats['mean_intensity']:.1f}, Median: {stats['median_intensity']:.1f}\n"
            
            if self.current_calibration:
                # Add scaled derivations
                mpp = self.current_calibration.microns_per_pixel_x
                # total field of view
                fov_w_mm = (self.frozen_frame.width * mpp) / 1000.0
                fov_h_mm = (self.frozen_frame.height * mpp) / 1000.0
                res_text += f"Calibrated FOV: {fov_w_mm:.2f} x {fov_h_mm:.2f} mm"
                
            self.lbl_stats.setText(res_text)
            
            # Add a visual RectROI just to represent the analyzed region (entire image for now)
            w = self.frozen_frame.width
            h = self.frozen_frame.height
            roi = pg.RectROI([0, 0], [w, h], pen='r', movable=False, resizable=False)
            self.image_view.getView().addItem(roi)
            self.analysis_rois.append(roi)
            
            self.last_analysis_run = AnalysisRun(
                analysis_run_id=run_id,
                source_frame_hash=hash_bytes(self.frozen_frame.jpeg_bytes),
                roi_ids=[],
                algorithm="THRESHOLD_CONNECTED_COMPONENTS",
                algorithm_version="1.0",
                parameters={"threshold": threshold},
                results={"num_features": num_features, "stats": stats},
                created_utc=int(time.time() * 1000)
            )

    def _capture_frame(self):
        if not self.frozen_frame:
            return
            
        os.makedirs(".virtuallab/artifacts", exist_ok=True)
        capture_id = generate_id("CAP")
        jpeg_bytes = self.frozen_frame.jpeg_bytes
        img_hash = hash_bytes(jpeg_bytes)
        
        # 1. Save exact original JPEG
        img_path = f".virtuallab/artifacts/{capture_id}.jpg"
        with open(img_path, "wb") as f:
            f.write(jpeg_bytes)
            
        # 2. Save metadata JSON
        meta_path = f".virtuallab/artifacts/{capture_id}.metadata.json"
        meta = {
            "source_device_id": self.frozen_frame.device_id,
            "camera_id": self.frozen_frame.camera_id,
            "logical_camera_id": self.frozen_frame.logical_camera_id,
            "physical_camera_id": self.frozen_frame.physical_camera_id,
            "frame_sequence": self.frozen_frame.frame_sequence,
            "device_timestamp_ns": self.frozen_frame.device_timestamp_ns,
            "received_utc_ns": self.frozen_frame.received_utc_ns,
            "message_type": self.frozen_frame.message_type,
            "representation": self.frozen_frame.representation
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
            
        meta_hash = hash_bytes(json.dumps(meta).encode('utf-8'))
        
        # 3. Save analysis run if any
        analysis_hash = None
        analysis_id = None
        if hasattr(self, 'last_analysis_run') and self.last_analysis_run:
            anl_path = f".virtuallab/artifacts/{self.last_analysis_run.analysis_run_id}.json"
            anl_data = {
                "analysis_run_id": self.last_analysis_run.analysis_run_id,
                "algorithm": self.last_analysis_run.algorithm,
                "parameters": self.last_analysis_run.parameters,
                "results": self.last_analysis_run.results
            }
            with open(anl_path, "w") as f:
                json.dump(anl_data, f, indent=2)
            analysis_hash = hash_bytes(json.dumps(anl_data).encode('utf-8'))
            analysis_id = self.last_analysis_run.analysis_run_id
            
        # Determine event type based on origin message_type
        event_type = "OPTICAL_ANALYSIS_SNAPSHOT_COMMITTED"
        if self.frozen_frame.message_type == "CAMERA_SCIENTIFIC_FRAME":
            event_type = "SCIENTIFIC_MICROSCOPE_FRAME_COMMITTED"
            
        payload = {
            "capture_id": capture_id,
            "analysis_run_id": analysis_id,
            "optical_setup_id": self.current_setup.setup_id,
            "calibration_id": self.current_calibration.calibration_id if self.current_calibration else None,
            "source_frame_hash": img_hash,
            "image_artifact_hash": img_hash,
            "metadata_artifact_hash": meta_hash,
            "analysis_artifact_hash": analysis_hash,
            "scientific_state": "MEASURED" if not analysis_id else "DERIVED",
            "representation": self.frozen_frame.representation,
            "timestamp": int(time.time() * 1000)
        }
        
        self.workspace.ledger.append(
            event_id=generate_id("EVT"),
            actor=Actor(type="SYSTEM", id="virtual_lab"),
            event_type=event_type,
            payload=payload
        )
        
        QMessageBox.information(self, "Scientific Capture", f"Successfully committed {event_type} artifact:\n{capture_id}")
