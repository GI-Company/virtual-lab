#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$HOME/BitVision-Fortran/native_3d}"
cd "$ROOT"
[ -f src/bitvision3d.f90 ] || { echo "Missing native_3d/src/bitvision3d.f90"; exit 1; }
command -v python3 >/dev/null || { echo "Python 3 required"; exit 1; }
if command -v gfortran >/dev/null; then
  FC="$(command -v gfortran)"
elif command -v brew >/dev/null && [ -x "$(brew --prefix gcc)/bin/gfortran" ]; then
  FC="$(brew --prefix gcc)/bin/gfortran"
else
  echo "GNU Fortran not found. Run: brew install gcc"
  exit 1
fi
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/state.f90" <<'BV3D_STATE'
  ! Live terminal viewer (coordinates/attributes are screen-space only).
  integer, parameter :: MW=60, MH=30, SR=38, SCW=130
  character(len=1), save :: scr(SR,SCW) = ' '
  integer, save :: scl(SR,SCW) = 0
  type watch_t
     integer :: upd=0, ntr=0, ptr=0, tlife(2)=0, flash=0, msglife=0
     integer :: lastact(4,2)=2, nmatch=0, wins(3)=0
     real(dp) :: radius=R_FINAL, lastmiss(2)=0.0_dp, fx=0.0_dp, fy=0.0_dp
     real(dp) :: trx(14,2)=0.0_dp, tryy(14,2)=0.0_dp
     real(dp) :: tox(2)=0.0_dp, toy(2)=0.0_dp, toyaw(2)=0.0_dp, tolen(2)=0.0_dp
     character(len=64) :: ckname='latest.bin'
     character(len=128) :: msg=' '
  end type watch_t

  interface
     function c_usleep(usecs) bind(C, name='usleep') result(rc)
        import :: c_int
        integer(c_int), value :: usecs
        integer(c_int) :: rc
     end function c_usleep
  end interface
BV3D_STATE
cat > "$TMP/watch.f90" <<'BV3D_WATCH'
  ! LIVE TERMINAL VIEWER  (bitvision3d watch)
  !
  ! Plays RED vs BLUE with the sampled policies from the newest
  ! checkpoint and draws it with ANSI graphics. Run it in a second
  ! terminal tab while `train` runs: every new match reloads
  ! checkpoints/latest.bin, so you watch the agents improve.
  ! ====================================================================

  function colcode(c) result(s)
    integer, intent(in) :: c
    character(len=5) :: s
    select case (c)
    case (1); s = achar(27)//'[91m'
    case (2); s = achar(27)//'[94m'
    case (3); s = achar(27)//'[93m'
    case (4); s = achar(27)//'[92m'
    case (5); s = achar(27)//'[90m'
    case (6); s = achar(27)//'[97m'
    case (7); s = achar(27)//'[96m'
    case default; s = achar(27)//'[0m'
    end select
  end function colcode

  subroutine scr_clear()
    scr = ' '
    scl = 0
  end subroutine scr_clear

  subroutine scr_cell(r, c, ch, color)
    integer, intent(in) :: r, c, color
    character(len=1), intent(in) :: ch
    if (r < 1 .or. r > SR .or. c < 1 .or. c > SCW) return
    scr(r, c) = ch
    scl(r, c) = color
  end subroutine scr_cell

  subroutine scr_text(r, c, s, color)
    integer, intent(in) :: r, c, color
    character(len=*), intent(in) :: s
    integer :: i
    do i = 1, len(s)
       call scr_cell(r, c + i - 1, s(i:i), color)
    end do
  end subroutine scr_text

  subroutine scr_flush()
    character(len=60000) :: buf
    integer :: p, r, c, cur, n
    character(len=5) :: cc
    p = 0
    buf(1:3) = achar(27)//'[H'
    p = 3
    do r = 1, SR
       cur = -1
       do c = 1, SCW
          if (scl(r, c) /= cur) then
             cur = scl(r, c)
             cc = colcode(cur)
             n = len_trim(cc)
             buf(p+1:p+n) = cc(1:n)
             p = p + n
          end if
          p = p + 1
          buf(p:p) = scr(r, c)
       end do
       buf(p+1:p+5) = achar(27)//'[0m'//achar(10)
       p = p + 5
    end do
    write(*, '(a)', advance='no') buf(1:p)
    flush(6)
  end subroutine scr_flush

  function act_words(act) result(s)
    integer, intent(in) :: act(4)
    character(len=64) :: s
    character(len=5) :: yw(3), pw(3), tw(3)
    yw = ['LEFT ', 'hold ', 'RIGHT']
    pw = ['DOWN ', 'level', 'UP   ']
    tw = ['slow ', 'hold ', 'FAST ']
    s = 'yaw '//yw(act(1))//' pitch '//pw(act(2))//' thr '//tw(act(3))//merge(' FIRE', '     ', act(4) == 2)
  end function act_words

  subroutine watch_render(ar, w, banner)
    type(arena_t), intent(in) :: ar
    type(watch_t), intent(in) :: w
    character(len=*), intent(in) :: banner
    integer :: a, k, r, c, i, rowz(2), idx, s, ns
    real(dp) :: ye, pe, dist, dz, t, x, y, hd
    character(len=1) :: gl(0:7)
    character(len=100) :: line
    integer :: colr(2)
    character(len=1) :: lab(2), trl(2)

    gl = ['>', '/', '^', char(92), '<', '/', 'v', char(92)]
    colr = [1, 2]
    lab = ['R', 'B']
    trl = ['.', ',']

    call scr_clear()
    call scr_text(1, 2, 'BITVISION 3D DUEL  -  live view (sampled policies)        Ctrl-C to quit', 6)

    ! ---- map frame -------------------------------------------------
    do c = 1, MW + 2
       call scr_cell(2, c, '-', 5)
       call scr_cell(MH + 3, c, '-', 5)
    end do
    do r = 3, MH + 2
       call scr_cell(r, 1, '|', 5)
       call scr_cell(r, MW + 2, '|', 5)
    end do
    call scr_cell(2, 1, '+', 5); call scr_cell(2, MW + 2, '+', 5)
    call scr_cell(MH + 3, 1, '+', 5); call scr_cell(MH + 3, MW + 2, '+', 5)

    ! ---- trails ----------------------------------------------------
    do a = 1, 2
       do k = 1, w%ntr
          call map_rc(w%trx(k, a), w%tryy(k, a), r, c)
          call scr_cell(r, c, trl(a), colr(a))
       end do
    end do

    ! ---- shot tracers (horizontal projection) ------------------------
    do a = 1, 2
       if (w%tlife(a) > 0) then
          ns = int(w%tolen(a) / 8.0_dp)
          do s = 0, ns
             t = 8.0_dp * real(s, dp)
             x = modulo(w%tox(a) + t * cos(w%toyaw(a)), WORLD)
             y = modulo(w%toy(a) + t * sin(w%toyaw(a)), WORLD)
             call map_rc(x, y, r, c)
             call scr_cell(r, c, ':', 3)
          end do
       end if
    end do

    ! ---- hit flash -------------------------------------------------
    if (w%flash > 0) then
       call map_rc(w%fx, w%fy, r, c)
       call scr_cell(r, c, '*', 3)
       call scr_cell(r, c - 1, '+', 3); call scr_cell(r, c + 1, '+', 3)
       call scr_cell(r - 1, c, '+', 3); call scr_cell(r + 1, c, '+', 3)
    end if

    ! ---- agents ----------------------------------------------------
    do a = 1, 2
       call map_rc(ar%x(a, 1), ar%y(a, 1), r, c)
       idx = modulo(nint(ar%yaw(a, 1) / (0.25_dp * PI)), 8)
       call scr_cell(r, c, gl(idx), colr(a))
       if (c < MW + 1) call scr_cell(r, c + 1, lab(a), colr(a))
    end do

    ! ---- altitude gauge --------------------------------------------
    call scr_text(2, 64, 'alt', 6)
    call scr_text(MH + 3, 64, 'R  B', 6)
    do r = 3, MH + 2
       call scr_cell(r, 65, '|', 5)
       call scr_cell(r, 68, '|', 5)
    end do
    do a = 1, 2
       rowz(a) = 3 + nint((1.0_dp - (ar%z(a, 1) - ZMIN) / (ZMAX - ZMIN)) * real(MH - 1, dp))
       rowz(a) = max(3, min(MH + 2, rowz(a)))
    end do
    call scr_cell(rowz(1), 65, 'R', 1)
    call scr_cell(rowz(2), 68, 'B', 2)

    ! ---- HUD -------------------------------------------------------
    call aim_abs(ar, 1, 1, ye, pe, dist)
    dz = ar%z(2, 1) - ar%z(1, 1)

    write(line, '(a,a,a,i0)') 'checkpoint ', trim(w%ckname), '   update ', w%upd
    call scr_text(3, 72, trim(line), 7)
    write(line, '(a,f6.1,a)') 'hit radius ', w%radius, '   (final 18.0)'
    call scr_text(4, 72, trim(line), 7)
    write(line, '(a,i4,a,i0)') 'tick ', ar%ticks(1), ' / ', MAX_TICKS
    call scr_text(5, 72, trim(line), 7)

    call scr_text(7, 72, 'SCORE', 6)
    write(line, '(a,i2)') 'RED  ', ar%score(1, 1)
    call scr_text(7, 79, trim(line), 1)
    write(line, '(a,i2)') 'BLUE ', ar%score(2, 1)
    call scr_text(7, 90, trim(line), 2)
    call scr_text(7, 100, '(first to 10)', 5)

    do a = 1, 2
       write(line, '(a,a,f5.0,a,f6.1,a,f5.1,a,i1)') merge('RED  ', 'BLUE ', a == 1), ' z', ar%z(a, 1), &
            '  pitch', ar%pitch(a, 1) / DEG, '  spd', ar%speed(a, 1), '  cd', ar%cd(a, 1)
       call scr_text(8 + a, 72, trim(line), colr(a))
    end do

    write(line, '(a,f6.0,a,f7.0)') 'range ', dist, '    dz (B-R) ', dz
    call scr_text(12, 72, trim(line), 7)

    do a = 1, 2
       call aim_abs(ar, 1, a, ye, pe, hd)
       write(line, '(a,a,f6.1,a,f6.1,a)') merge('RED  ', 'BLUE ', a == 1), 'aim err  yaw', ye / DEG, '  pitch', pe / DEG, ' deg'
       call scr_text(13 + a, 72, trim(line), colr(a))
       if (ye < 12.0_dp * DEG .and. pe < 12.0_dp * DEG) call scr_text(13 + a, 108, 'ON TARGET', 3)
    end do

    call scr_text(17, 72, 'RED  '//trim(act_words(w%lastact(:, 1))), 1)
    call scr_text(18, 72, 'BLUE '//trim(act_words(w%lastact(:, 2))), 2)

    write(line, '(a,f7.1,a,f7.1)') 'last shot miss distance  R', w%lastmiss(1), '   B', w%lastmiss(2)
    call scr_text(20, 72, trim(line), 5)
    if (w%msglife > 0) call scr_text(21, 72, trim(w%msg), 3)
    if (len_trim(banner) > 0) call scr_text(23, 72, trim(banner), 6)

    write(line, '(a,i0)') 'matches watched ', w%nmatch
    call scr_text(25, 72, trim(line), 7)
    write(line, '(a,i0,a,i0,a,i0)') 'RED wins ', w%wins(1), '   BLUE wins ', w%wins(2), '   draws ', w%wins(3)
    call scr_text(26, 72, trim(line), 7)

    call scr_text(28, 72, 'map: top-down, x east / y north (edges wrap)', 5)
    call scr_text(29, 72, 'arrow = heading, R/B = who, : = shot, * = hit', 5)
    call scr_text(30, 72, '. , = recent trail.  hit needs ray within radius', 5)
    call scr_text(31, 72, 'in 3D, so altitude gap (gauge, dz) can cause a miss', 5)
  end subroutine watch_render

  subroutine map_rc(x, y, r, c)
    real(dp), intent(in) :: x, y
    integer, intent(out) :: r, c
    c = 2 + max(0, min(MW - 1, int(modulo(x, WORLD) / WORLD * real(MW, dp))))
    r = 3 + max(0, min(MH - 1, int((1.0_dp - modulo(y, WORLD) / WORLD) * real(MH, dp))))
  end subroutine map_rc

  subroutine run_watch(delay_ms, which, rmode, max_matches)
    integer, intent(in) :: delay_ms, max_matches
    character(len=*), intent(in) :: which, rmode
    real(dp) :: th(NP, 2), thn(NP, 2), best, radius, prog, x(NIN), lp, v, rew(2), hx, hy
    type(opt_t) :: opt(2)
    type(arena_t) :: ar
    type(watch_t) :: w
    type(tickinfo_t) :: ti
    integer :: upd, a, k, dec, act(4, 2), seedv, tc, rate, rc, updn, wrow
    logical :: ok, ended
    character(len=64) :: path
    character(len=72) :: banner
    integer(c_int) :: us

    if (trim(which) == 'best') then
       path = 'checkpoints/best.bin'
    else
       path = 'checkpoints/latest.bin'
    end if
    w%ckname = path

    do
       call load_ckpt(trim(path), ok, upd, th, opt, best)
       if (ok) exit
       print '(a)', 'waiting for '//trim(path)//' (training writes it every 25 updates; run `train` in another tab) ...'
       rc = c_usleep(2000000_c_int)
    end do

    write(*, '(a)', advance='no') achar(27)//'[2J' 
    call system_clock(tc, rate)
    seedv = 1000 + mod(tc, 100000)
    us = int(max(1, min(900, delay_ms)) * 1000, c_int)

    do
       call load_ckpt(trim(path), ok, updn, thn, opt, best)
       if (ok) then
          th = thn
          upd = updn
       end if
       if (trim(rmode) == 'final') then
          radius = R_FINAL
       else
          call curriculum(upd + 1, radius, prog)
       end if
       w%upd = upd; w%radius = radius
       w%ntr = 0; w%ptr = 0; w%tlife = 0; w%flash = 0; w%msglife = 0
       w%msg = ' '; w%lastmiss = 0.0_dp; w%lastact = 2
       banner = ' '
       seedv = seedv + 1
       call arena_init(ar, 1, seedv)
       ended = .false.

       do dec = 1, MAX_TICKS / NREP + 1
          do a = 1, 2
             call observe(ar, 1, a, x)
             call policy_act(th(:, a), x, act(:, a), lp, v, .false., ar%rng(1))
          end do
          w%lastact = act
          do k = 1, NREP
             call tick(ar, 1, act, radius, 1.0_dp, rew, ti)

             w%ptr = mod(w%ptr, 14) + 1
             w%ntr = min(w%ntr + 1, 14)
             do a = 1, 2
                w%trx(w%ptr, a) = ar%x(a, 1)
                w%tryy(w%ptr, a) = ar%y(a, 1)
             end do
             do a = 1, 2
                w%tlife(a) = max(0, w%tlife(a) - 1)
                if (ti%fired(a)) then
                   w%tlife(a) = 3
                   w%tox(a) = ar%x(a, 1); w%toy(a) = ar%y(a, 1); w%toyaw(a) = ar%yaw(a, 1)
                   w%lastmiss(a) = ti%miss(a)
                   hx = wd(ar%x(a, 1), ar%x(3 - a, 1)); hy = wd(ar%y(a, 1), ar%y(3 - a, 1))
                   w%tolen(a) = merge(sqrt(hx*hx + hy*hy), 260.0_dp, ti%hit(a))
                   if (ti%hit(a)) then
                      w%flash = 8
                      w%fx = ar%x(3 - a, 1); w%fy = ar%y(3 - a, 1)
                      write(w%msg, '(a,a,f6.1,a)') merge('RED ', 'BLUE', a == 1), ' HIT !   (ray miss ', ti%miss(a), ')'
                      w%msglife = 90
                   end if
                end if
             end do
             w%flash = max(0, w%flash - 1)
             w%msglife = max(0, w%msglife - 1)

             call watch_render(ar, w, banner)
             call scr_flush()
             rc = c_usleep(us)
             if (ti%ended) then
                ended = .true.
                exit
             end if
          end do
          if (ended) exit
       end do

       w%nmatch = w%nmatch + 1
       if (ti%win(1)) then
          w%wins(1) = w%wins(1) + 1
          write(banner, '(a,i0,a,i0,a)') 'MATCH OVER: RED wins  ', ar%score(1, 1), ' - ', ar%score(2, 1), '  BLUE'
       else if (ti%win(2)) then
          w%wins(2) = w%wins(2) + 1
          write(banner, '(a,i0,a,i0,a)') 'MATCH OVER: BLUE wins  ', ar%score(2, 1), ' - ', ar%score(1, 1), '  RED'
       else
          w%wins(3) = w%wins(3) + 1
          write(banner, '(a,i0,a,i0,a)') 'MATCH OVER: draw / timeout  RED ', ar%score(1, 1), '  BLUE ', ar%score(2, 1), ' '
       end if
       call watch_render(ar, w, banner)
       call scr_flush()
       if (max_matches > 0) then
          if (w%nmatch >= max_matches) exit
       end if
       rc = c_usleep(1500000_c_int)
    end do
    write(*, '(a)', advance='no') achar(27)//'[0m'//achar(10)
  end subroutine run_watch
BV3D_WATCH
python3 - "$ROOT/src/bitvision3d.f90" "$TMP" <<'BV3D_PATCH'
from pathlib import Path
import sys
src=Path(sys.argv[1]); tmp=Path(sys.argv[2]); s=src.read_text()
if 'subroutine run_watch(' in s:
    raise SystemExit('Live viewer already installed; no changes made.')
required=['module bv3d','  end type opt_t','contains','end module bv3d',"  case ('playback')",'  function int_arg(k, def) result(v)']
for item in required:
    if item not in s:
        raise SystemExit('Unexpected source structure: '+item)
state=(tmp/'state.f90').read_text()
viewer=(tmp/'watch.f90').read_text()
s=s.replace('  use, intrinsic :: iso_fortran_env, only: int64, real64',
    '  use, intrinsic :: iso_fortran_env, only: int64, real64\n  use, intrinsic :: iso_c_binding, only: c_int',1)
s=s.replace('  end type opt_t', '  end type opt_t\n\n'+state,1)
s=s.replace('end module bv3d', viewer+'\nend module bv3d',1)
s=s.replace("  case ('playback')\n     call run_playback()", "  case ('playback')\n     call run_playback()\n  case ('watch')\n     call run_watch(int_arg(2,80), str_arg(3,'latest'), str_arg(4,'final'), int_arg(5,0))",1)
s=s.replace("  function int_arg(k, def) result(v)", """  function str_arg(k, def) result(v)
    integer, intent(in) :: k
    character(len=*), intent(in) :: def
    character(len=64) :: v
    v = def
    if (command_argument_count() >= k) call get_command_argument(k, v)
  end function str_arg

  function int_arg(k, def) result(v)""",1)
s=s.replace("'usage: bitvision3d selftest | train [updates] [envs] [rollout] [seed] | eval [matches] | playback'", 
"'usage: bitvision3d selftest | train [updates] [envs] [rollout] [seed] | eval [matches] | playback | watch [ms] [latest|best] [final|curriculum] [matches]'")
(tmp/'bitvision3d.f90').write_text(s)
BV3D_PATCH
mkdir -p "$TMP/mod" source_backups
"$FC" -O2 -fcheck=bounds -ffree-line-length-none -J "$TMP/mod" "$TMP/bitvision3d.f90" -o "$TMP/bitvision3d"
(cd "$TMP" && ./bitvision3d selftest)
cp src/bitvision3d.f90 "source_backups/bitvision3d_$(date +%Y%m%d_%H%M%S).f90"
cp "$TMP/bitvision3d.f90" src/bitvision3d.f90
./build.sh
printf '\nInstalled live viewer. Existing checkpoints and training metrics untouched.\n'
printf 'Open a second Terminal window and run:\n'
printf 'cd "%s" && ./build/bitvision3d watch 80 latest final\n' "$ROOT"
printf 'Stop watching with Ctrl-C; watch 1 latest final 1 plays just one match.\n'