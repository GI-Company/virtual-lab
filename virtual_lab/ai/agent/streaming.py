from enum import Enum
import json
import re

class StreamEventType(Enum):
    ANSWER_DELTA = "ANSWER_DELTA"
    TOOL_CALL_STARTED = "TOOL_CALL_STARTED"
    TOOL_CALL_COMPLETE = "TOOL_CALL_COMPLETE"
    PROPOSAL_COMPLETE = "PROPOSAL_COMPLETE"
    ACTION_COMPLETE = "ACTION_COMPLETE"
    OUTPUT_COMPLETE = "OUTPUT_COMPLETE"
    OUTPUT_INVALID = "OUTPUT_INVALID"
    RAW_TOKEN = "RAW_TOKEN"

class StreamingEnvelopeParser:
    def __init__(self, callback):
        self.callback = callback
        self.buffer = ""
        self.is_completed = False
        
        self.in_string = False
        self.escaped = False
        self.brace_depth = 0
        self.json_started = False
        
        self.last_emitted_answer_len = 0
        
    def feed(self, token: str):
        if self.is_completed:
            return
            
        self.buffer += token
        self.callback(StreamEventType.RAW_TOKEN, token)
        
        # State machine for brace depth and string parsing
        for c in token:
            if self.escaped:
                self.escaped = False
            elif c == '\\':
                self.escaped = True
            elif c == '"':
                self.in_string = not self.in_string
            elif not self.in_string:
                if c == '{':
                    self.brace_depth += 1
                    self.json_started = True
                elif c == '}':
                    self.brace_depth -= 1
                    
        # If we have started JSON and returned to 0 depth, it's complete
        if self.json_started and self.brace_depth <= 0 and not self.in_string:
            self.is_completed = True
            self._finalize()
            return
            
        # If we are inside the 'text' field of an answer, we can emit deltas
        # A simple heuristic: if we see "text": " and we are inside that string
        if self.json_started and self.in_string:
            text_match = re.search(r'"text"\s*:\s*"', self.buffer)
            if text_match:
                start_idx = text_match.end()
                if len(self.buffer) > start_idx:
                    # Everything from start_idx to the end of the buffer (minus trailing quote if any) is the text
                    # We have to handle escaped characters for real JSON. 
                    # For a quick streaming delta, we can just parse the substring using json.loads manually if it ends with quote,
                    # or just yield the raw suffix and let UI handle it.
                    # A better way: try parsing the partial JSON to see if we can extract "text".
                    # For simplicity, we just strip the start_idx and unescape manually.
                    raw_text = self.buffer[start_idx:]
                    if not self.in_string and raw_text.endswith('"'):
                        raw_text = raw_text[:-1]
                        
                    # Unescape basic sequences
                    raw_text = raw_text.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                    
                    if len(raw_text) > self.last_emitted_answer_len:
                        delta = raw_text[self.last_emitted_answer_len:]
                        self.last_emitted_answer_len = len(raw_text)
                        self.callback(StreamEventType.ANSWER_DELTA, delta)

    def _finalize(self):
        try:
            # Attempt to parse the completed JSON buffer
            start_idx = self.buffer.find('{')
            end_idx = self.buffer.rfind('}')
            if start_idx != -1 and end_idx != -1:
                clean_json = self.buffer[start_idx:end_idx+1]
                parsed = json.loads(clean_json)
                
                msg_type = parsed.get("type", "")
                if msg_type == "answer" or msg_type == "final_answer":
                    self.callback(StreamEventType.OUTPUT_COMPLETE, parsed)
                elif msg_type == "tool_call":
                    tool_name = parsed.get("tool_name", parsed.get("tool", ""))
                    if "propose" in tool_name:
                        self.callback(StreamEventType.PROPOSAL_COMPLETE, parsed)
                    elif tool_name in ["run_simulation", "acquire_scientific_frame", "control_instrument", "branch_experiment", "change_model_parameters"]:
                        self.callback(StreamEventType.ACTION_COMPLETE, parsed)
                    else:
                        self.callback(StreamEventType.TOOL_CALL_COMPLETE, parsed)
                else:
                    self.callback(StreamEventType.OUTPUT_COMPLETE, parsed)
            else:
                self.callback(StreamEventType.OUTPUT_INVALID, "No JSON object found")
        except Exception as e:
            self.callback(StreamEventType.OUTPUT_INVALID, str(e))
