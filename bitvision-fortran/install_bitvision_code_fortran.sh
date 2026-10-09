#!/usr/bin/env bash
# BitVision-Code — standalone native Fortran code-learning experiment
set -euo pipefail
ROOT="${1:-$HOME/BitVision-Fortran/native_code}"
mkdir -p "$ROOT/src" "$ROOT/build" "$ROOT/runs" "$ROOT/results" "$ROOT/checkpoints" "$ROOT/backups"
cd "$ROOT"
if [ -f src/bitvision_code.f90 ]; then
  BACKUP="backups/source-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$BACKUP"
  cp -p src/bitvision_code.f90 "$BACKUP/"
  for item in build.sh run-tests.sh build-compile.sh README.md; do
    if [ -f "$item" ]; then cp -p "$item" "$BACKUP/"; fi
  done
  if [ -f checkpoints/latest.bvc ]; then
    cp -p checkpoints/latest.bvc "$BACKUP/"
  fi
  echo "[BACKUP] Existing source/checkpoint copied to $BACKUP"
fi
if command -v brew >/dev/null 2>&1; then
  if ! command -v gfortran >/dev/null 2>&1 && [ ! -x "$(brew --prefix gcc 2>/dev/null)/bin/gfortran" ]; then
    brew install gcc
  fi
elif ! command -v gfortran >/dev/null 2>&1; then
  echo "GNU Fortran is required. Install Homebrew and run: brew install gcc" >&2
  exit 1
fi
cat > src/bitvision_code.f90 <<'BVC_FORTRAN_SOURCE'
module bv_code
  use iso_fortran_env, only: real64
  implicit none
  integer, parameter :: dp=real64, NT=6, NF=1024, NC=8
  integer, parameter :: NOPT=3, NPHRASE=6
  integer, parameter :: nsamples=18, ntrain=12
  real(dp), parameter :: LRC=0.35_dp, LRP=0.20_dp
  real(dp) :: cw(NT,NF), pw(NOPT,2,NT), ew(NC,NT), baseline(NT)
  integer :: episode=0, solved=0, compiles=0, attempts_total=0
  integer, allocatable :: rng(:)
  character(len=120), parameter :: prompts(NPHRASE,NT) = reshape([character(len=120) :: &
    'double the integer','multiply the input by two','twice the given number', &
    'return two times n','calculate two times the input','double n from the request', &
    'square the number','multiply integer by itself','compute n squared', &
    'return the second power of n','calculate square of input','find the square of n', &
    'absolute value of n','remove the sign from the integer','nonnegative magnitude of input', &
    'distance from zero for n','return abs of n','return the absolute magnitude of n', &
    'increment n by one','add one to the input','return the next integer', &
    'increase the number by one','one more than n','please increment integer n', &
    'return one when n is even otherwise zero','test whether number divisible by two', &
    'detect an even integer','is the input even','calculate the even parity flag', &
    'return an even flag for integer n', &
    'sign of integer minus one zero or plus one','return signum of n', &
    'negative zero positive classification','determine sign of number', &
    'output negative one or zero or positive one','calculate the sign of n' &
    ], [NPHRASE,NT])
contains
  function intent_name(task) result(name)
    integer,intent(in)::task
    character(len=16)::name
    select case(task)
    case(1);name='double'
    case(2);name='square'
    case(3);name='absolute value'
    case(4);name='increment'
    case(5);name='is even'
    case(6);name='sign'
    case default;name='unknown'
    end select
  end function

  subroutine initialize()
    integer :: i
    cw=0.0_dp; pw=0.0_dp; ew=0.0_dp; baseline=0.0_dp
    ! A modest compiler-safe initialization, not pretrained programming knowledge.
    pw(1,1,:)=1.0_dp
    pw(1,2,:)=1.0_dp
    episode=0; solved=0; compiles=0; attempts_total=0
    call random_seed(size=i)
    if (allocated(rng)) deallocate(rng)
    allocate(rng(i))
    rng=1977 + 37*[(i, i=1,size(rng))]
    call random_seed(put=rng)
  end subroutine

  function lower(s) result(t)
    character(len=*),intent(in):: s
    character(len=len(s)):: t
    integer :: i,c
    t=s
    do i=1,len(s)
       c=iachar(s(i:i))
       if(c>=65 .and. c<=90) t(i:i)=achar(c+32)
    end do
  end function

  logical function stopword(s) result(found)
    character(len=*),intent(in)::s
    select case(trim(s))
    case('n','the','of','to','a','an','by','for','integer','number','input', &
         'return','calculate','compute','write','determine','from','with','value', &
         'given','please','is','when','or','zero','one')
       found=.true.
    case default
       found=.false.
    end select
  end function

  subroutine vectorize(text,x)
    character(len=*),intent(in)::text
    real(dp),intent(out)::x(NF)
    character(len=:),allocatable::s
    integer::i,j,k,h,z,n,start,last
    x=0.0_dp
    s=' '//trim(lower(adjustl(text)))//' '
    n=len(s)
    ! Surface pattern features, independent of any external tokenizer.
    do i=1,n
       do k=3,4
          if(i+k-1>n)cycle
          h=0
          do j=i,i+k-1
             z=iachar(s(j:j))
             h=modulo(h*37+z,512)
          end do
          x(h+1)=x(h+1)+0.10_dp
       end do
    end do
    ! Stronger lexical concepts; common filler terms cannot overwhelm meaning.
    i=1
    do while(i<=n)
       if(.not.alphanumeric(s(i:i)))then
          i=i+1
          cycle
       end if
       start=i
       do while(i<=n)
          if(.not.alphanumeric(s(i:i)))exit
          i=i+1
       end do
       last=i-1
       if(stopword(s(start:last)))cycle
       h=0
       do j=start,last
          h=modulo(h*131+iachar(s(j:j)),512)
       end do
       x(513+h)=x(513+h)+3.0_dp
    end do
    x=x/max(sqrt(sum(x*x)),1.0e-9_dp)
  end subroutine

  subroutine softmax(logits,p)
    real(dp),intent(in)::logits(:)
    real(dp),intent(out)::p(size(logits))
    p=exp(max(-60.0_dp,min(60.0_dp,logits-maxval(logits))))
    p=p/max(sum(p),1.0e-30_dp)
  end subroutine

  integer function pick(p,greedy) result(a)
    real(dp),intent(in)::p(:)
    logical,intent(in)::greedy
    real(dp)::u,acc
    integer::i
    if(greedy) then
       a=maxloc(p,dim=1)
       return
    end if
    call random_number(u)
    acc=0.0_dp
    a=size(p)
    do i=1,size(p)
       acc=acc+p(i)
       if(u<acc) then
          a=i
          exit
       end if
    end do
  end function

  subroutine classify(prompt,task,probs,confidence)
    character(len=*),intent(in)::prompt
    integer,intent(out)::task
    real(dp),intent(out)::probs(NT),confidence
    real(dp)::x(NF)
    call vectorize(prompt,x)
    call softmax(matmul(cw,x),probs)
    task=maxloc(probs,dim=1)
    confidence=probs(task)
  end subroutine

  subroutine train_encoder(prompt,truth)
    character(len=*),intent(in)::prompt
    integer,intent(in)::truth
    real(dp)::x(NF),p(NT),delta(NT)
    integer::i,t
    call vectorize(prompt,x)
    call softmax(matmul(cw,x),p)
    delta=-p
    delta(truth)=delta(truth)+1.0_dp
    do t=1,NT
       do i=1,NF
          cw(t,i)=cw(t,i)+LRC*delta(t)*x(i)
       end do
    end do
  end subroutine

  function expr(task,choice) result(s)
    integer,intent(in)::task,choice
    character(len=100)::s
    s='n'
    select case(task)
    case(1)
       select case(choice)
       case(1);s='n * 2'
       case(2);s='n + n'
       case(3);s='n / 2'
       case(4);s='n ** 2'
       case(5);s='n + 1'
       case(6);s='abs(n)'
       case(7);s='0'
       case(8);s='n +'
       end select
    case(2)
       select case(choice)
       case(1);s='n ** 2'
       case(2);s='n * n'
       case(3);s='n + n'
       case(4);s='abs(n)'
       case(5);s='n / 2'
       case(6);s='n + 1'
       case(7);s='0'
       case(8);s='n +'
       end select
    case(3)
       select case(choice)
       case(1);s='abs(n)'
       case(2);s='max(n, -n)'
       case(3);s='n'
       case(4);s='-n'
       case(5);s='n * n'
       case(6);s='sign(1,n)'
       case(7);s='0'
       case(8);s='n +'
       end select
    case(4)
       select case(choice)
       case(1);s='n + 1'
       case(2);s='1 + n'
       case(3);s='n - 1'
       case(4);s='n + n'
       case(5);s='n ** 2'
       case(6);s='abs(n)'
       case(7);s='n'
       case(8);s='n +'
       end select
    case(5)
       select case(choice)
       case(1);s='merge(1, 0, mod(n,2)==0)'
       case(2);s='merge(1, 0, modulo(n,2)==0)'
       case(3);s='mod(n,2)'
       case(4);s='merge(1, 0, n>0)'
       case(5);s='n / 2'
       case(6);s='0'
       case(7);s='1'
       case(8);s='n +'
       end select
    case(6)
       select case(choice)
       case(1);s='max(-1, min(1, n))'
       case(2);s='merge(1, merge(-1, 0, n<0), n>0)'
       case(3);s='sign(1, n)'
       case(4);s='abs(n)'
       case(5);s='n'
       case(6);s='merge(1, -1, n>=0)'
       case(7);s='0'
       case(8);s='n +'
       end select
    end select
  end function

  integer function expected(task,n) result(v)
    integer,intent(in)::task,n
    select case(task)
    case(1);v=n*2
    case(2);v=n*n
    case(3);v=abs(n)
    case(4);v=n+1
    case(5);v=merge(1,0,mod(n,2)==0)
    case(6);v=max(-1,min(1,n))
    case default;v=0
    end select
  end function

  subroutine generate(task,opts,stream,delay_ms)
    integer,intent(in)::task,opts(3),delay_ms
    logical,intent(in)::stream
    integer::u
    character(len=180)::line(6)
    line(1)='integer function solve(n)'
    line(2)='  implicit none'
    select case(opts(1))
    case(1);line(3)='  integer, intent(in) :: n'
    case(2);line(3)='  integer intent(in) :: n'
    case default;line(3)='  integer, intent(in) n'
    end select
    select case(opts(2))
    case(1);line(4)='  solve = '//trim(expr(task,opts(3)))
    case(2);line(4)='  solve == '//trim(expr(task,opts(3)))
    case default;line(4)='  solve := '//trim(expr(task,opts(3)))
    end select
    line(5)='end function solve'
    line(6)=' '
    open(newunit=u,file='runs/solve.f90',status='replace',action='write')
    write(u,'(a)') trim(line(1)),trim(line(2)),trim(line(3)),trim(line(4)),trim(line(5))
    close(u)
    if(stream) then
       write(*,'(a)') '  [TOKEN STREAM / FORTRAN SOURCE]'
       call stream_source('runs/solve.f90',delay_ms)
    end if
  end subroutine

  subroutine sleep_ms(ms)
    integer,intent(in)::ms
    ! Portable microdelay for macOS and Linux through a bound libc call.
    block
      use iso_c_binding, only:c_int
      interface
         function usleep_c(usec) bind(c,name='usleep') result(rc)
           import c_int
           integer(c_int),value::usec
           integer(c_int)::rc
         end function
      end interface
      integer(c_int)::rc
      if(ms>0)rc=usleep_c(int(min(100,ms)*1000,c_int))
    end block
  end subroutine

  logical function alphanumeric(ch) result(a)
    character(len=1),intent(in)::ch
    integer::k
    k=iachar(ch)
    a=(k>=48 .and. k<=57).or.(k>=65.and.k<=90).or.(k>=97.and.k<=122).or.ch=='_'
  end function

  subroutine stream_source(path,delay_ms)
    character(len=*),intent(in)::path
    integer,intent(in)::delay_ms
    character(len=512)::line
    integer::u,ios,i,j,n
    open(newunit=u,file=path,status='old',action='read')
    do
       read(u,'(a)',iostat=ios)line
       if(ios/=0) exit
       n=len_trim(line);i=1
       do while(i<=n)
          j=i
          if(alphanumeric(line(i:i)))then
             do while(j<=n)
                if(.not.alphanumeric(line(j:j)))exit
                j=j+1
             end do
          else if(line(i:i)==' ')then
             do while(j<=n)
                if(line(j:j)/=' ')exit
                j=j+1
             end do
          else
             j=i+1
          end if
          write(*,'(a)',advance='no')line(i:j-1)
          flush(6)
          if(line(i:i)/=' ')call sleep_ms(delay_ms)
          i=j
       end do
       write(*,*)
    end do
    close(u)
  end subroutine

  subroutine make_driver(task,heldout)
    integer,intent(in)::task
    logical,intent(in)::heldout
    integer::u,i,n,v
    integer,parameter::inputs(nsamples)=[-13,-11,-9,-7,-4,-3,-2,-1,0,1,2,3,4,5,8,9,11,12]
    open(newunit=u,file='runs/check.f90',status='replace',action='write')
    write(u,'(a)')'program check'
    write(u,'(a)')'  implicit none'
    write(u,'(a)')'  integer :: i, ok, got'
    write(u,'(a)')'  integer, external :: solve'
    write(u,'(a)')'  integer, parameter :: n(18)=[ &'
    write(u,'(a)')'    -13,-11,-9,-7,-4,-3,-2,-1,0,1,2,3,4,5,8,9,11,12 ]'
    write(u,'(a)')'  integer, parameter :: answer(18)=[ &'
    do i=1,nsamples
       n=inputs(i);v=expected(task,n)
       if(i/=nsamples)then
          write(u,'(a,i0,a)')'    ',v,', &'
       else
          write(u,'(a,i0,a)')'    ',v,' ]'
       end if
    end do
    write(u,'(a)')'  ok=0'
    if(heldout)then
       write(u,'(a)')'  do i=1,18'
    else
       write(u,'(a)')'  do i=1,12'
    end if
    write(u,'(a)')'    got=solve(n(i))'
    write(u,'(a)')'    if(got==answer(i))ok=ok+1'
    write(u,'(a)')'    if(i<=3.or.i>=16)then'
    write(u,'(a)')'      write(*,''(a,i0,a,i0,a,i0)'') ''n='',n(i),'' expected='',answer(i),'' got='',got'
    write(u,'(a)')'    end if'
    write(u,'(a)')'  end do'
    write(u,'(a)')'  print *, ''RESULT '',ok' 
    write(u,'(a)')'end program check'
    close(u)
  end subroutine

  subroutine execute_candidate(task,trace,heldout,passed,compile_ok,exitcode)
    integer,intent(in)::task
    logical,intent(in)::heldout
    logical,intent(in)::trace
    integer,intent(out)::passed,exitcode
    logical,intent(out)::compile_ok
    integer::istat,u,ios
    character(len=500)::line
    passed=0; compile_ok=.false.;exitcode=-1
    call make_driver(task,heldout)
    call execute_command_line( &
       './build-compile.sh > runs/compile.log 2>&1', &
       exitstat=istat)
    if(istat/=0) then
       if(trace)then
          write(*,'(a)')'  [COMPILER] FAILED:'
          call show_error('runs/compile.log')
       end if
       exitcode=1
       return
    end if
    compile_ok=.true.
    if(trace)write(*,'(a)')'  [COMPILER] SUCCESS: executable created'
    call execute_command_line('bash ./run-tests.sh > runs/test.log 2>&1',exitstat=istat)
    exitcode=istat
    if(istat/=0)then
       if(trace)then
          write(*,'(a)')'  [EXECUTION] failed or exceeded limits:'
          call show_first('runs/test.log',3)
       end if
       return
    end if
    open(newunit=u,file='runs/test.log',status='old',action='read',iostat=ios)
    if(ios/=0)return
    do
       read(u,'(a)',iostat=ios)line
       if(ios/=0)exit
       if(index(line,'RESULT')>0)then
          block
            integer::pos,ios2
            pos=index(line,'RESULT')+len('RESULT')
            read(line(pos:),*,iostat=ios2)passed
            if(ios2/=0)passed=0
          end block
       end if
    end do
    close(u)
    if(trace)then
       if(heldout)then
          write(*,'(a,i0,a,i0)')'  [EXECUTION] passed ',passed,' / ',nsamples
       else
          write(*,'(a,i0,a,i0)')'  [EXECUTION] passed ',passed,' / ',ntrain
       end if
       if(passed<nsamples)call show_first('runs/test.log',4)
    end if
  end subroutine

  subroutine show_error(path)
    character(len=*),intent(in)::path
    character(len=500)::line
    integer::u,ios
    open(newunit=u,file=path,status='old',action='read',iostat=ios)
    if(ios/=0)return
    do
       read(u,'(a)',iostat=ios)line
       if(ios/=0)exit
       if(index(line,'Error:')>0.or.index(line,'Fatal Error:')>0)then
          print '(a)','     '//trim(line)
          close(u)
          return
       end if
    end do
    close(u)
    call show_first(path,4)
  end subroutine

  subroutine show_first(path,how_many)
    character(len=*),intent(in)::path
    integer,intent(in)::how_many
    integer::u,ios,i
    character(len=500)::line
    open(newunit=u,file=path,status='old',action='read',iostat=ios)
    if(ios/=0)return
    do i=1,how_many
       read(u,'(a)',iostat=ios)line
       if(ios/=0)exit
       print '(a)','     '//trim(line)
    end do
    close(u)
  end subroutine

  subroutine sample_actions(task,opts,greedy,exclude)
    integer,intent(in)::task
    integer,intent(out)::opts(3)
    logical,intent(in)::greedy
    logical,intent(in),optional::exclude(NC)
    real(dp)::p3(3),p8(NC),tmp(NC)
    integer::i
    call softmax(pw(:,1,task),p3)
    opts(1)=pick(p3,greedy)
    call softmax(pw(:,2,task),p3)
    opts(2)=pick(p3,greedy)
    tmp=ew(:,task)
    if(present(exclude))then
       do i=1,NC
          if(exclude(i))tmp(i)=-100.0_dp
       end do
       if(all(exclude))tmp=ew(:,task)
    end if
    call softmax(tmp,p8)
    opts(3)=pick(p8,greedy)
  end subroutine

  subroutine update_policy(task,opts,passed,compiled)
    integer,intent(in)::task,opts(3),passed
    logical,intent(in)::compiled
    real(dp)::p3(3),p8(NC),rewards(3),adv,oldbase
    integer::d,k
    rewards=0.0_dp
    if(compiled)then
       rewards(1:2)=0.45_dp
       rewards(3)=real(passed,dp)/real(ntrain,dp)*2.7_dp-0.60_dp
    else
       ! Compiler feedback assigns blame to the earliest invalid slot.
       ! Do not penalize a correct expression for a malformed declaration.
       if(opts(1)/=1)then
          rewards(1)=-1.4_dp
       else if(opts(2)/=1)then
          rewards(2)=-1.4_dp
       else
          rewards(3)=-1.0_dp
       end if
    end if
    do d=1,2
       call softmax(pw(:,d,task),p3)
       do k=1,3
          pw(k,d,task)=pw(k,d,task)+LRP*rewards(d)*(merge(1.0_dp,0.0_dp,k==opts(d))-p3(k))
       end do
    end do
    oldbase=baseline(task)
    adv=rewards(3)-oldbase
    baseline(task)=0.98_dp*oldbase+0.02_dp*rewards(3)
    call softmax(ew(:,task),p8)
    do k=1,NC
       ew(k,task)=ew(k,task)+LRP*adv*(merge(1.0_dp,0.0_dp,k==opts(3))-p8(k))
    end do
  end subroutine

  subroutine save_checkpoint(path)
    character(len=*),optional,intent(in)::path
    integer::u,i,istat
    character(len=256)::dest,tmp
    dest='checkpoints/latest.bvc'
    if(present(path))dest=path
    tmp=trim(dest)//'.tmp'
    call random_seed(size=i)
    if(allocated(rng))deallocate(rng)
    allocate(rng(i))
    call random_seed(get=rng)
    open(newunit=u,file=trim(tmp),status='replace',access='stream',form='unformatted')
    write(u)20261009,3,episode,solved,compiles,attempts_total,i
    write(u)cw,pw,ew,baseline,rng
    close(u)
    call execute_command_line('mv '//trim(tmp)//' '//trim(dest),exitstat=istat)
    if(istat/=0)error stop 'Checkpoint rename failed'
  end subroutine

  subroutine load_checkpoint(ok,path)
    logical,intent(out)::ok
    character(len=*),optional,intent(in)::path
    character(len=256)::dest
    integer::u,ios,magic,version,sz,expect_sz
    dest='checkpoints/latest.bvc'
    if(present(path))dest=path
    inquire(file=trim(dest),exist=ok)
    if(.not.ok)return
    open(newunit=u,file=trim(dest),access='stream',form='unformatted',status='old',iostat=ios)
    if(ios/=0)then
       ok=.false.;return
    end if
    read(u,iostat=ios)magic,version,episode,solved,compiles,attempts_total,sz
    if(ios/=0)then
       ok=.false.;close(u);return
    end if
    call random_seed(size=expect_sz)
    if(magic/=20261009.or.version/=3.or.sz/=expect_sz)then
       ok=.false.;close(u);return
    end if
    if(allocated(rng))deallocate(rng)
    allocate(rng(sz))
    read(u,iostat=ios)cw,pw,ew,baseline,rng
    close(u)
    ok=ios==0
    if(ok)call random_seed(put=rng)
  end subroutine

  subroutine archive_success(task)
    integer,intent(in)::task
    integer::status
    character(len=150)::cmd
    write(cmd,'(a,i0,a)')'cp runs/solve.f90 results/task_',task,'_solved.f90'
    call execute_command_line(trim(cmd),exitstat=status)
  end subroutine

  subroutine trial(truth,phrase,trace,delay_ms,maxtries,success,tries_used,correct_class)
    integer,intent(in)::truth,phrase,delay_ms,maxtries
    logical,intent(in)::trace
    logical,intent(out)::success,correct_class
    integer,intent(out)::tries_used
    integer::predicted,opts(3),passed,code,tries
    real(dp)::p(NT),confidence
    logical::compiled,exclude(NC)
    character(len=120)::prompt
    prompt=prompts(phrase,truth)
    call classify(prompt,predicted,p,confidence)
    correct_class=predicted==truth
    if(trace)then
       print '(a)','============================================================'
       print '(a)','NATURAL-LANGUAGE REQUEST: '//trim(prompt)
       print '(a,f5.1,a)','Encoder predicted '//trim(intent_name(predicted))//' (confidence ', &
             100.0_dp*confidence,'%)'
       print '(a)','Supervised training target: '//trim(intent_name(truth))
       print '(a)','Training verifier: 12 inputs; 6 additional inputs reserved for evaluation'
    end if
    exclude=.false.;success=.false.;tries_used=0
    do tries=1,maxtries
       tries_used=tries
       call sample_actions(truth,opts,.false.,exclude)
       if(trace)write(*,'(a,i0,a,i0,a)')'[GENERATE] Attempt ',tries,', candidate expression ',opts(3),':'
       call generate(truth,opts,trace,delay_ms)
       call execute_candidate(truth,trace,.false.,passed,compiled,code)
       attempts_total=attempts_total+1
       if(compiled)compiles=compiles+1
       call update_policy(truth,opts,passed,compiled)
       if(passed==ntrain.and.compiled.and.code==0)then
          success=.true.
          if(trace)print '(a)','[VERIFIER] PASS: all 12 training tests passed. Candidate accepted.'
       call archive_success(truth)
          exit
       end if
       if(trace)then
          if(.not.compiled)then
             if(opts(1)/=1)then
                print '(a)','[REPAIR PLAN] Declaration is malformed; prioritize repairing the input type.'
             else if(opts(2)/=1)then
                print '(a)','[REPAIR PLAN] Assignment operator is malformed; restore Fortran = syntax.'
             else
                print '(a)','[REPAIR PLAN] Expression has a syntax/type error; replace the expression.'
             end if
          else
             print '(a)','[REPAIR PLAN] Code compiles but behavior is wrong: try a different expression.'
          end if
          print '(a)','[LEARNING] Updated policy weights from compiler/test feedback.'
       end if
       if(compiled)exclude(opts(3))=.true.
       call train_encoder(prompt,truth)
       ! When language classification is wrong, correct it before attempting next edit.
       call classify(prompt,predicted,p,confidence)
    end do
    call train_encoder(prompt,truth)
    if(trace.and..not.success)print '(a)','[VERIFIER] Unsolved within attempt budget; saved learning signal.'
  end subroutine

  subroutine training(steps,delay_ms,verbose_every)
    integer,intent(in)::steps,delay_ms,verbose_every
    integer::k,t,ph,tries,acc,successes,comp_before,start_ep
    logical::success,ok,correct
    call load_checkpoint(ok)
    if(ok)then
       print '(a,i0)','[RESUME] Loaded model at episode ',episode
    else
       call initialize()
       print '(a)','[INIT] Fresh native policy; no checkpoint found'
    end if
    start_ep=episode
    successes=0;acc=0;comp_before=compiles
    do k=1,steps
       episode=episode+1
       t=modulo(episode-1,NT)+1
       ph=modulo((episode-1)/NT,NPHRASE-1)+1
       call trial(t,ph,mod(k-1,verbose_every)==0,delay_ms,5,success,tries,correct)
       if(success)then
          solved=solved+1;successes=successes+1
       end if
       if(correct)acc=acc+1
       if(mod(k,25)==0.or.k==steps)then
          write(*,'(a,i0,a,i0,a,i0,a,i0,a,i0)') &
            '[METRICS] episode ',episode,' solved in window ',successes, &
            ' correct intent ',acc,' compiled in window ',compiles-comp_before,' attempts total ',attempts_total
          successes=0;acc=0;comp_before=compiles
          call save_checkpoint()
          call append_metrics()
       end if
    end do
    call save_checkpoint()
    write(*,'(a,i0)')'[DONE] Checkpoint saved at episode ',episode
  end subroutine

  subroutine append_metrics()
    integer::u,ios
    logical::exist
    inquire(file='results/metrics.csv',exist=exist)
    open(newunit=u,file='results/metrics.csv',status='unknown',position='append',iostat=ios)
    if(ios/=0)return
    if(.not.exist)write(u,'(a)')'episode,solved_cumulative,compiled_cumulative,attempts_cumulative'
    write(u,'(i0,a,i0,a,i0,a,i0)')episode,',',solved,',',compiles,',',attempts_total
    close(u)
  end subroutine

  subroutine inference(prompt,delay_ms)
    character(len=*),intent(in)::prompt
    integer,intent(in)::delay_ms
    integer::task,opts(3),passed,code,tries
    real(dp)::p(NT),confidence
    logical::ok,compiled,exclude(NC),accepted
    call load_checkpoint(ok)
    if(.not.ok)then
       print '(a)','No trained checkpoint yet. Run: ./build/bitvision_code train 250'
       return
    end if
    call classify(prompt,task,p,confidence)
    print '(a)','REQUEST: '//trim(prompt)
    print '(a,f5.1,a)','[INTENT] '//trim(intent_name(task))//' confidence ',100*confidence,' %'
    if(confidence<0.30_dp)then
       print '(a)','[WARNING] Low confidence; this is a closed six-task system, not general natural-language coding.'
    end if
    exclude=.false.;accepted=.false.
    do tries=1,5
       if(tries==1)then
          call sample_actions(task,opts,.true.)
       else
          opts(1:2)=1
          call sample_actions(task,opts,.false.,exclude)
          opts(1:2)=1
       end if
       print '(a,i0)','[ATTEMPT] ',tries
       call generate(task,opts,.true.,delay_ms)
       call execute_candidate(task,.true.,.true.,passed,compiled,code)
       if(compiled.and.passed==nsamples.and.code==0)then
          accepted=.true.
          call archive_success(task)
          exit
       end if
       print '(a)','[SELF-REPAIR] Failed validation; replace expression or invalid syntax.'
       exclude(opts(3))=.true.
    end do
    if(accepted)then
       print '(a)','[ACCEPTED] All inferred-task verification tests passed.'
    else
       print '(a)','[UNSOLVED] No valid solution found within five attempts.'
    end if
    print '(a)','[LIMITATION] Tests verify the inferred task, not unrestricted English instructions.'
  end subroutine

  subroutine evaluate()
    integer::task,phrase,guess,opts(3),passed,code,good,compiled_count,langgood
    real(dp)::p(NT),cf
    logical::ok,compiled
    call load_checkpoint(ok)
    if(.not.ok)then
       print '(a)','No checkpoint found.';return
    end if
    good=0;compiled_count=0;langgood=0
    do task=1,NT
       phrase=NPHRASE ! sixth prompt per task is withheld from training
       call classify(prompts(phrase,task),guess,p,cf)
       if(guess==task)langgood=langgood+1
       call sample_actions(guess,opts,.true.)
       call generate(guess,opts,.false.,0)
       call execute_candidate(task,.false.,.true.,passed,compiled,code)
       if(compiled)compiled_count=compiled_count+1
       if(passed==nsamples.and.compiled.and.code==0)good=good+1
       write(*,'(a,i0,a,i0,a,i0,a,l1,a,i0)')'task ',task,' predicted ',guess, &
            ' candidate ',opts(3),' compiled ',compiled,' passed ',passed
    end do
    write(*,'(a,i0,a,i0,a,i0,a,i0,a)')'[EVAL] correct languages ',langgood, &
         '/6, compiled ',compiled_count,'/6, solved ',good,'/6'
  end subroutine

  subroutine selftest()
    integer::task,opts(3),passed,code
    logical::compiled,ok
    call initialize()
    do task=1,NT
       opts=[1,1,1]
       call generate(task,opts,.false.,0)
       call execute_candidate(task,.false.,.true.,passed,compiled,code)
       if(.not.compiled.or.passed/=nsamples)then
          print '(a,i0,a,i0)','FAIL: reference implementation task ',task,' pass ',passed
          stop 1
       end if
    end do
    opts=[2,1,1]
    call generate(1,opts,.false.,0)
    call execute_candidate(1,.false.,.true.,passed,compiled,code)
    if(compiled)then
       print '(a)','FAIL: invalid syntax compiled'
       stop 1
    end if
    opts=[1,1,3]
    call generate(1,opts,.false.,0)
    call execute_candidate(1,.false.,.true.,passed,compiled,code)
    if(.not.compiled.or.passed==nsamples)then
       print '(a)','FAIL: semantic error undetected'
       stop 1
    end if
    call save_checkpoint('checkpoints/selftest.bvc')
    call load_checkpoint(ok,'checkpoints/selftest.bvc')
    if(.not.ok)then
       print '(a)','FAIL: checkpoint roundtrip';stop 1
    end if
    print '(a)','PASS six compiled reference tasks + syntax rejection + semantic rejection + checkpoint roundtrip'
  end subroutine
end module bv_code

program main
  use bv_code
  implicit none
  character(len=30)::cmd,arg
  character(len=1000)::prompt
  integer::steps,delay_ms,verbose_every,ios
  call get_command_argument(1,cmd)
  select case(trim(cmd))
  case('train')
     steps=250;delay_ms=5;verbose_every=12
     call get_command_argument(2,arg)
     if(len_trim(arg)>0)read(arg,*,iostat=ios)steps
     call get_command_argument(3,arg)
     if(len_trim(arg)>0)read(arg,*,iostat=ios)delay_ms
     call get_command_argument(4,arg)
     if(len_trim(arg)>0)read(arg,*,iostat=ios)verbose_every
     if(steps<1.or.steps>1000000.or.delay_ms<0.or.verbose_every<1)then
        print '(a)','Invalid parameters';stop 1
     end if
     call training(steps,delay_ms,verbose_every)
  case('infer')
     call get_command_argument(2,prompt)
     if(len_trim(prompt)==0)then
        print '(a)','Usage: infer "square the number"';stop 1
     end if
     delay_ms=15
     call get_command_argument(3,arg)
     if(len_trim(arg)>0)read(arg,*,iostat=ios)delay_ms
     call inference(trim(prompt),delay_ms)
  case('eval')
     call evaluate()
  case('selftest')
     call selftest()
  case default
     print '(a)','BitVision-Code — native Fortran compiler-guided learning lab'
     print '(a)','Usage:'
     print '(a)','  ./build/bitvision_code selftest'
     print '(a)','  ./build/bitvision_code train [episodes=250] [token_delay_ms=5] [detailed_every=12]'
     print '(a)','  ./build/bitvision_code infer "square the number" [token_delay_ms=15]'
     print '(a)','  ./build/bitvision_code eval'
     print '(a)','Supports six closed-form integer tasks, not arbitrary code generation.'
  end select
end program main
BVC_FORTRAN_SOURCE
cat > build.sh <<'BVC_BUILD_SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build runs results checkpoints
if command -v brew >/dev/null 2>&1 && [ -x "$(brew --prefix gcc)/bin/gfortran" ]; then
  FC="$(brew --prefix gcc)/bin/gfortran"
else
  FC="$(command -v gfortran)"
fi
cat > build-compile.sh <<EOF
#!/usr/bin/env bash
set -euo pipefail
"$FC" -O0 -fcheck=all -fbacktrace -ffree-line-length-none runs/solve.f90 runs/check.f90 -o runs/candidate
EOF
chmod +x build-compile.sh run-tests.sh
"$FC" -O2 -std=f2008 -Wall -Wextra -fcheck=all -ffree-line-length-none \
  src/bitvision_code.f90 -o build/bitvision_code
printf '[BUILD] Native BitVision-Code compiled with %s\n' "$FC"
BVC_BUILD_SCRIPT
cat > run-tests.sh <<'BVC_RUN_SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
ulimit -t 3
ulimit -c 0
./runs/candidate
BVC_RUN_SCRIPT
cat > README.md <<'BVC_README'
# BitVision-Code (native Fortran compiler-feedback experiment)

This is a **small, restricted research environment**, not a general coding language model and not a port of BitVision 3D combat weights. It has a trained bag-of-character/word intent encoder, a trainable action policy selecting a small set of Fortran syntax/expression choices, and an online compiler/test reward loop. Code is displayed in lexical tokens as it is emitted from selected templates. The repair trace is rule-based feedback handling rather than internal hidden reasoning.

Supported integer tasks: double, square, absolute value, increment by one, evenness flag (1/0), signum (-1/0/1).

Commands (from the native_code folder):

```bash
./build/bitvision_code train 250 10 1 # 250 episodes; 10ms between lexical tokens; show every repair attempt
./build/bitvision_code eval           # 6 held-out prompt phrasings and 6 unseen test inputs each
./build/bitvision_code infer "square the number" 18
./build/bitvision_code selftest
```

`train` resumes from `checkpoints/latest.bvc`; `selftest` uses a separate checkpoint path and will not reset training. The training reward comes from compiling and evaluating the generated functions on 12 labeled inputs. Evaluation uses 18 inputs per task (12 training-verifier values plus 6 additional held-out values). Evaluation prompt formulations are withheld but remain closely related to the 5 training prompts per task. Six tasks is far too little to infer generalization to open-domain natural-language programming.

Logs: `results/metrics.csv`; accepted code: `results/task_<number>_solved.f90`; latest attempt: `runs/solve.f90`; compiler diagnostics: `runs/compile.log`; execution: `runs/test.log`.

Safety: only a fixed, bounded expression grammar is emitted, not arbitrary source supplied by a user. Compiled programs run under a per-process CPU time limit. This is NOT a security sandbox for arbitrary generated code; for an open-domain agent, implement proper isolation (containers/VM, seccomp/system policy, no network, memory and wall-clock limits).
BVC_README
chmod +x build.sh run-tests.sh
./build.sh
./build/bitvision_code selftest
printf '\n[START] Demonstrating real compiler-feedback training and live lexical token output...\n'
./build/bitvision_code train 12 8 1
printf '\n[READY] Installed at %s\n' "$ROOT"
printf 'Continue watching: cd "%s" && ./build/bitvision_code train 250 10 1\n' "$ROOT"
printf 'Evaluate:         cd "%s" && ./build/bitvision_code eval\n' "$ROOT"
printf 'Try a request:    cd "%s" && ./build/bitvision_code infer "square the number" 18\n' "$ROOT"