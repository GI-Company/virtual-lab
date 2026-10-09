#!/usr/bin/env bash
# BitVision-Code V2 — verified all-Fortran token-structured training installer
set -euo pipefail
ROOT="${1:-$HOME/BitVision-Fortran/native_code_v2}"
if ! command -v gfortran >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1 || [ ! -x "$(brew --prefix gcc)/bin/gfortran" ]; then
    echo "GNU Fortran is missing. On macOS run: brew install gcc" >&2
    exit 1
  fi
fi
mkdir -p "$ROOT/src" "$ROOT/build" "$ROOT/runs" "$ROOT/results" "$ROOT/checkpoints" "$ROOT/backups"
cd "$ROOT"
if [ -f src/bitvision_code_v2.f90 ]; then
  BACKUP="backups/source-$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$BACKUP"
  cp -p src/bitvision_code_v2.f90 "$BACKUP/"
  for FILE in build.sh build-compile.sh run-tests.sh README.md; do
    if [ -f "$FILE" ]; then cp -p "$FILE" "$BACKUP/"; fi
  done
fi
# Deliberately never touch ~/BitVision-Fortran/native_code/checkpoints/latest.bvc
# or ~/BitVision-Fortran/native_3d/checkpoints/.
cat > src/bitvision_code_v2.f90 <<'BITVISION_V2_FORTRAN'
module bvcode_v2
  use iso_fortran_env, only: real64
  implicit none
  private
  integer, parameter :: dp=real64, NT=12, NF=1024, NS=14, NM=8, NST=4
  integer, parameter :: NTRAIN=12, NTEST=18, NPH=6
  integer, parameter :: S_MODE=1, S_DECL=2, S_ASSIGN=3, S_LHS=4, S_OP=5, S_RHS=6, &
     S_UNARY=7, S_PRED=8, S_YES=9, S_NO=10, S_LOOP=11, S_LIMIT=12, S_INIT=13, S_BODY=14
  integer, parameter :: ST_BASE=1, ST_SYNTAX=2, ST_SEMANTIC=3, ST_RUNTIME=4
  integer, parameter :: ACOUNT(NS)=[4,3,3,3,5,5,5,5,4,4,2,3,2,2]
  integer, parameter :: MAGIC=20261009, VERSION=4
  real(dp), parameter :: INTENT_LR=0.55_dp, POLICY_LR=0.22_dp
  real(dp) :: iw(NT,NF), w(NM,NS,NT,NST), base(NT)
  ! Exact-candidate cache avoids recompiling previously verified programs.
  integer,parameter :: CACHE_MAX=12000
  integer :: cache_size=0,cache_tokens(NS,CACHE_MAX),cache_task(CACHE_MAX), &
      cache_pass(CACHE_MAX),cache_feedback(CACHE_MAX)
  logical :: cache_heldout(CACHE_MAX),cache_compiled(CACHE_MAX)
  integer :: episode=0, cumulative_solved=0, cumulative_compiled=0, cumulative_attempts=0
  character(len=144), parameter :: prompts(NPH,NT)=reshape([character(len=144):: &
    'double the number','multiply n by two','twice n','calculate two times the integer','make the input twice as large','return double the given integer', &
    'square the number','multiply n by itself','second power of n','compute the square of integer','n squared','calculate the squared input', &
    'absolute value of integer','magnitude of n','remove the minus sign','distance from zero','nonnegative magnitude','take absolute value of given number', &
    'increment the integer','add one to n','next integer','increase n by one','n plus one','return the successor of n', &
    'return one if even otherwise zero','test for even number','even integer flag','detect whether n is divisible by two','evenness indicator','return 1 for even n and 0 otherwise', &
    'classify sign of n','negative zero positive classification','signum function','return minus one zero or one based on sign','sign of integer','determine if input is negative zero or positive', &
    'triple the integer','three times the input','multiply n by three','make integer threefold','return three times n','compute triple of n', &
    'decrement n by one','subtract one from integer','previous integer','n minus one','reduce input by 1','return the predecessor of n', &
    'return one if odd else zero','odd integer flag','detect odd n','not divisible by two','parity is odd','return 1 if n is odd and 0 otherwise', &
    'clamp integer to between minus five and five','limit n to range negative five through five', &
    'bound the input in negative five positive five','clip n to plus or minus five','cap the absolute limit at five', &
    'return n constrained to the interval from -5 to 5', &
    'sum integers from one to n','triangular number of n','add all positive integers up to n', &
    'accumulate i from 1 to n','one through n summation','calculate the sum from 1 through max(0,n)', &
    'factorial of n','multiply integers one through n','n factorial for nonnegative integers', &
    'product from one to n','compute factorial result','return factorial for the given small integer' &
    ],[NPH,NT])
  type :: program_t
     integer :: tok(NS)=1
  end type
  public :: run_train,run_eval,run_infer,run_selftest,run_usage,save_ckpt,load_ckpt
contains
  function task_name(t) result(s)
    integer,intent(in)::t
    character(len=24)::s
    select case(t)
    case(1);s='double'
    case(2);s='square'
    case(3);s='abs'
    case(4);s='increment'
    case(5);s='even'
    case(6);s='sign'
    case(7);s='triple'
    case(8);s='decrement'
    case(9);s='odd'
    case(10);s='clamp'
    case(11);s='sum 1..n'
    case(12);s='factorial'
    case default;s='unsupported'
    end select
  end function
  function slot_name(k) result(s)
    integer,intent(in)::k
    character(len=20)::s
    select case(k)
    case(1);s='structure'
    case(2);s='declaration'
    case(3);s='assignment'
    case(4);s='left operand'
    case(5);s='operator'
    case(6);s='right operand'
    case(7);s='unary call'
    case(8);s='predicate'
    case(9);s='true branch'
    case(10);s='false branch'
    case(11);s='loop reduction'
    case(12);s='loop bound'
    case(13);s='loop initializer'
    case(14);s='loop element'
    end select
  end function
  subroutine initialize()
    integer::i,n
    iw=0.0_dp;w=0.0_dp;base=0.0_dp;cache_size=0
    episode=0;cumulative_solved=0;cumulative_compiled=0;cumulative_attempts=0
    call random_seed(size=n)
    block
      integer,allocatable::seed(:)
      allocate(seed(n));seed=424242+29*[(i,i=1,n)]
      call random_seed(put=seed)
    end block
  end subroutine
  function lowered(s) result(t)
    character(len=*),intent(in)::s
    character(len=len(s))::t
    integer::i,v
    t=s
    do i=1,len(s)
      v=iachar(t(i:i))
      if(v>=65.and.v<=90)t(i:i)=achar(v+32)
    end do
  end function
  logical function allowed(ch)
    character,intent(in)::ch
    integer::k
    k=iachar(ch)
    allowed=(k>=48.and.k<=57).or.(k>=97.and.k<=122)
  end function
  logical function stopword(word)
    character(len=*),intent(in)::word
    select case(word)
    case('the','a','an','to','of','for','from','and','n','integer','input','number','return','calculate', &
         'compute','result','given','is','by','or','one','zero','if','else','with')
      stopword=.true.
    case default
      stopword=.false.
    end select
  end function
  subroutine features(s,x)
    character(len=*),intent(in)::s
    real(dp),intent(out)::x(NF)
    character(len=:),allocatable::q
    integer::i,j,k,h,start,finish,n
    x=0.0_dp;q=' '//trim(lowered(s))//' ';n=len(q)
    do i=1,n
      do k=3,4
        if(i+k-1>n)cycle
        h=0
        do j=i,i+k-1
          h=modulo(h*37+iachar(q(j:j)),512)
        end do
        x(1+h)=x(1+h)+0.10_dp
      end do
    end do
    i=1
    do while(i<=n)
      if(.not.allowed(q(i:i)))then
        i=i+1;cycle
      end if
      start=i
      do while(i<=n)
        if(.not.allowed(q(i:i)))exit
        i=i+1
      end do
      finish=i-1
      if(stopword(q(start:finish)))cycle
      h=0
      do j=start,finish
        h=modulo(h*131+iachar(q(j:j)),512)
      end do
      x(513+h)=x(513+h)+3.0_dp
    end do
    x=x/max(sqrt(sum(x*x)),1.0e-12_dp)
  end subroutine
  subroutine normexp(y,p)
    real(dp),intent(in)::y(:)
    real(dp),intent(out)::p(size(y))
    p=exp(max(-60.0_dp,min(0.0_dp,y-maxval(y))))
    p=p/max(sum(p),1.0e-20_dp)
  end subroutine
  integer function choose(p,greedy) result(k)
    real(dp),intent(in)::p(:)
    logical,intent(in)::greedy
    real(dp)::u,acc
    integer::i
    if(greedy)then
       k=maxloc(p,dim=1);return
    end if
    call random_number(u)
    acc=0.0_dp;k=size(p)
    do i=1,size(p)
       acc=acc+p(i)
       if(u<=acc)then
          k=i;return
       end if
    end do
  end function
  subroutine predict(prompt,t,confidence)
    character(len=*),intent(in)::prompt
    integer,intent(out)::t
    real(dp),intent(out)::confidence
    real(dp)::x(NF),p(NT)
    call features(prompt,x)
    call normexp(matmul(iw,x),p)
    t=maxloc(p,dim=1);confidence=p(t)
  end subroutine
  subroutine teach_intent(prompt,truth)
    character(len=*),intent(in)::prompt
    integer,intent(in)::truth
    real(dp)::x(NF),p(NT)
    integer::t
    call features(prompt,x);call normexp(matmul(iw,x),p)
    do t=1,NT
       iw(t,:)=iw(t,:)+INTENT_LR*(merge(1.0_dp,0.0_dp,t==truth)-p(t))*x
    end do
  end subroutine
  function correct_program(t) result(g)
    integer,intent(in)::t
    type(program_t)::g
    g%tok=1
    select case(t)
    case(1);g%tok([S_MODE,S_LHS,S_OP,S_RHS])=[1,1,3,2]
    case(2);g%tok([S_MODE,S_LHS,S_OP,S_RHS])=[1,1,3,4]
    case(3);g%tok([S_MODE,S_UNARY])=[2,1]
    case(4);g%tok([S_MODE,S_LHS,S_OP,S_RHS])=[1,1,1,1]
    case(5);g%tok([S_MODE,S_PRED,S_YES,S_NO])=[3,1,1,2]
    case(6);g%tok([S_MODE,S_UNARY])=[2,3]
    case(7);g%tok([S_MODE,S_LHS,S_OP,S_RHS])=[1,1,3,3]
    case(8);g%tok([S_MODE,S_LHS,S_OP,S_RHS])=[1,1,2,1]
    case(9);g%tok([S_MODE,S_PRED,S_YES,S_NO])=[3,2,1,2]
    case(10);g%tok([S_MODE,S_UNARY])=[2,4]
    case(11);g%tok([S_MODE,S_LOOP,S_LIMIT,S_INIT,S_BODY])=[4,1,1,1,1]
    case(12);g%tok([S_MODE,S_LOOP,S_LIMIT,S_INIT,S_BODY])=[4,2,1,2,1]
    end select
  end function
  function token_word(slot,value) result(z)
    integer,intent(in)::slot,value
    character(len=80)::z
    z='?'
    select case(slot)
    case(S_MODE)
       select case(value)
       case(1);z='binary expression'
       case(2);z='unary expression'
       case(3);z='if / else'
       case(4);z='bounded do loop'
       end select
    case(S_DECL)
       select case(value)
       case(1);z='integer, intent(in) :: n'
       case(2);z='integer intent(in) :: n'
       case(3);z='integer, intent(in) n'
       end select
    case(S_ASSIGN)
       select case(value)
       case(1);z='='
       case(2);z='=='
       case(3);z=':='
       end select
    case(S_LHS)
       select case(value)
       case(1);z='n'
       case(2);z='1'
       case(3);z='0'
       end select
    case(S_OP)
       select case(value)
       case(1);z='+'
       case(2);z='-'
       case(3);z='*'
       case(4);z='**'
       case(5);z='/'
       end select
    case(S_RHS)
       select case(value)
       case(1);z='1'
       case(2);z='2'
       case(3);z='3'
       case(4);z='n'
       case(5);z='0'
       end select
    case(S_UNARY)
       select case(value)
       case(1);z='abs(n)'
       case(2);z='-n'
       case(3);z='max(-1,min(1,n))'
       case(4);z='max(-5,min(5,n))'
       case(5);z='sign(1,n)'
       end select
    case(S_PRED)
       select case(value)
       case(1);z='mod(n,2)==0'
       case(2);z='mod(n,2)/=0'
       case(3);z='n>0'
       case(4);z='n<0'
       case(5);z='n==0'
       end select
    case(S_YES,S_NO)
       select case(value)
       case(1);z='1'
       case(2);z='0'
       case(3);z='-1'
       case(4);z='n'
       end select
    case(S_LOOP)
       select case(value)
       case(1);z='+'
       case(2);z='*'
       end select
    case(S_LIMIT)
       select case(value)
       case(1);z='max(0,min(10,n))'
       case(2);z='max(0,min(10,abs(n)))'
       case(3);z='min(10,n)'
       end select
    case(S_INIT)
       select case(value)
       case(1);z='0'
       case(2);z='1'
       end select
    case(S_BODY)
       select case(value)
       case(1);z='i'
       case(2);z='n'
       end select
    end select
  end function
  subroutine active_slots(g,a,n)
    type(program_t),intent(in)::g
    integer,intent(out)::a(NS),n
    a=0;n=3;a(1:3)=[S_MODE,S_DECL,S_ASSIGN]
    select case(g%tok(S_MODE))
    case(1);n=6;a(4:6)=[S_LHS,S_OP,S_RHS]
    case(2);n=4;a(4)=S_UNARY
    case(3);n=6;a(4:6)=[S_PRED,S_YES,S_NO]
    case(4);n=7;a(4:7)=[S_LOOP,S_LIMIT,S_INIT,S_BODY]
    end select
  end subroutine
  subroutine probs(t,slot,state,p)
    integer,intent(in)::t,slot,state
    real(dp),intent(out)::p(NM)
    real(dp)::z(NM)
    z=-100.0_dp
    z(1:ACOUNT(slot))=w(1:ACOUNT(slot),slot,t,ST_BASE)
    if(state/=ST_BASE)z(1:ACOUNT(slot))=z(1:ACOUNT(slot))+w(1:ACOUNT(slot),slot,t,state)
    call normexp(z,p)
  end subroutine
  subroutine sample_slot(t,g,k,state,greedy)
    integer,intent(in)::t,k,state
    type(program_t),intent(inout)::g
    logical,intent(in)::greedy
    real(dp)::p(NM)
    call probs(t,k,state,p)
    g%tok(k)=choose(p(1:ACOUNT(k)),greedy)
  end subroutine
  subroutine sample_program(t,g,greedy)
    integer,intent(in)::t
    type(program_t),intent(out)::g
    logical,intent(in)::greedy
    integer::a(NS),n,i
    g%tok=1
    call sample_slot(t,g,S_MODE,ST_BASE,greedy)
    call active_slots(g,a,n)
    do i=2,n
       call sample_slot(t,g,a(i),ST_BASE,greedy)
    end do
  end subroutine
  subroutine reinforce(t,k,state,choice,reward)
    integer,intent(in)::t,k,state,choice
    real(dp),intent(in)::reward
    real(dp)::p(NM),step
    integer::j
    call probs(t,k,state,p)
    step=POLICY_LR*max(-3.0_dp,min(3.0_dp,reward))
    do j=1,ACOUNT(k)
       w(j,k,t,ST_BASE)=w(j,k,t,ST_BASE)+step*(merge(1.0_dp,0.0_dp,j==choice)-p(j))
       if(state/=ST_BASE) w(j,k,t,state)=w(j,k,t,state)+0.40_dp*step* &
           (merge(1.0_dp,0.0_dp,j==choice)-p(j))
    end do
  end subroutine
  subroutine reinforce_result(t,g,passed,compiled)
    integer,intent(in)::t,passed
    type(program_t),intent(in)::g
    logical,intent(in)::compiled
    integer::a(NS),n,i,k
    real(dp)::reward,old
    call active_slots(g,a,n)
    reward=-1.2_dp+2.0_dp*real(passed,dp)/NTRAIN
    if(.not.compiled)reward=-1.5_dp
    if(compiled.and.passed==NTRAIN)reward=4.0_dp
    old=base(t);base(t)=0.98_dp*old+0.02_dp*reward
    do i=1,n
       k=a(i)
       call reinforce(t,k,ST_BASE,g%tok(k),0.30_dp*(reward-old))
    end do
  end subroutine
  subroutine teach_program(t)
    integer,intent(in)::t
    type(program_t)::g
    integer::a(NS),n,i,k
    g=correct_program(t)
    call active_slots(g,a,n)
    do i=1,n
       k=a(i)
       call reinforce(t,k,ST_BASE,g%tok(k),0.85_dp)
    end do
  end subroutine
  integer function oracle(t,n) result(v)
    integer,intent(in)::t,n
    integer::i
    select case(t)
    case(1);v=2*n
    case(2);v=n*n
    case(3);v=abs(n)
    case(4);v=n+1
    case(5);v=merge(1,0,mod(n,2)==0)
    case(6);v=max(-1,min(1,n))
    case(7);v=3*n
    case(8);v=n-1
    case(9);v=merge(1,0,mod(n,2)/=0)
    case(10);v=max(-5,min(5,n))
    case(11)
       v=0
       do i=1,max(0,n)
          v=v+i
       end do
    case(12)
       v=1
       do i=1,max(0,n)
          v=v*i
       end do
    case default;v=0
    end select
  end function
  subroutine create_source(g,stream,delay)
    type(program_t),intent(in)::g
    logical,intent(in)::stream
    integer,intent(in)::delay
    character(len=200)::lines(12),rhs
    integer::u,n,i
    lines=' ';n=0
    n=n+1;lines(n)='integer function solve(n)'
    n=n+1;lines(n)='  implicit none'
    n=n+1;lines(n)='  '//trim(token_word(S_DECL,g%tok(S_DECL)))
    select case(g%tok(S_MODE))
    case(1)
       rhs=trim(token_word(S_LHS,g%tok(S_LHS)))//' '//trim(token_word(S_OP,g%tok(S_OP)))//' '// &
             trim(token_word(S_RHS,g%tok(S_RHS)))
       n=n+1;lines(n)='  solve '//trim(token_word(S_ASSIGN,g%tok(S_ASSIGN)))//' '//trim(rhs)
    case(2)
       n=n+1;lines(n)='  solve '//trim(token_word(S_ASSIGN,g%tok(S_ASSIGN)))//' '// &
                           trim(token_word(S_UNARY,g%tok(S_UNARY)))
    case(3)
       n=n+1;lines(n)='  if ('//trim(token_word(S_PRED,g%tok(S_PRED)))//') then'
       n=n+1;lines(n)='    solve '//trim(token_word(S_ASSIGN,g%tok(S_ASSIGN)))//' '// &
                           trim(token_word(S_YES,g%tok(S_YES)))
       n=n+1;lines(n)='  else'
       n=n+1;lines(n)='    solve '//trim(token_word(S_ASSIGN,g%tok(S_ASSIGN)))//' '// &
                           trim(token_word(S_NO,g%tok(S_NO)))
       n=n+1;lines(n)='  end if'
    case(4)
       n=n+1;lines(n)='  integer :: i'
       n=n+1;lines(n)='  solve '//trim(token_word(S_ASSIGN,g%tok(S_ASSIGN)))//' '// &
                           trim(token_word(S_INIT,g%tok(S_INIT)))
       n=n+1;lines(n)='  do i = 1, '//trim(token_word(S_LIMIT,g%tok(S_LIMIT)))
       n=n+1;lines(n)='    solve '//trim(token_word(S_ASSIGN,g%tok(S_ASSIGN)))//' solve '// &
                           trim(token_word(S_LOOP,g%tok(S_LOOP)))//' '//trim(token_word(S_BODY,g%tok(S_BODY)))
       n=n+1;lines(n)='  end do'
    end select
    n=n+1;lines(n)='end function solve'
    open(newunit=u,file='runs/solve.f90',status='replace',action='write')
    do i=1,n
      write(u,'(a)')trim(lines(i))
    end do
    close(u)
    if(stream)then
       print '(a)','  [TOKEN STREAM: sampled structure and grammar choices]'
       call stream_file('runs/solve.f90',delay)
    end if
  end subroutine
  subroutine sleep_ms(ms)
    use iso_c_binding,only:c_int
    integer,intent(in)::ms
    interface
      function usleep_c(usec) bind(c,name='usleep') result(rc)
        import c_int
        integer(c_int),value::usec
        integer(c_int)::rc
      end function
    end interface
    integer(c_int)::rc
    if(ms>0)rc=usleep_c(int(min(100,ms)*1000,c_int))
  end subroutine
  logical function isword(c)
    character,intent(in)::c
    integer::k
    k=iachar(c)
    isword=(k>=48.and.k<=57).or.(k>=65.and.k<=90).or.(k>=97.and.k<=122).or.c=='_'
  end function
  subroutine stream_file(path,delay)
    character(len=*),intent(in)::path
    integer,intent(in)::delay
    character(len=600)::line
    integer::u,ios,i,j,n
    open(newunit=u,file=path,status='old')
    do
       read(u,'(a)',iostat=ios)line
       if(ios/=0)exit
       n=len_trim(line);i=1
       do while(i<=n)
          j=i+1
          if(isword(line(i:i)))then
             do while(j<=n)
                if(.not.isword(line(j:j)))exit
                j=j+1
             end do
          else if(line(i:i)==' ')then
             do while(j<=n)
                if(line(j:j)/=' ')exit
                j=j+1
             end do
          end if
          write(*,'(a)',advance='no')line(i:j-1)
          flush(6)
          if(line(i:i)/=' ')call sleep_ms(delay)
          i=j
       end do
       write(*,'(a)')''
    end do
    close(u)
  end subroutine
  subroutine make_tests(t,heldout)
    integer,intent(in)::t
    logical,intent(in)::heldout
    integer,parameter::inputs(NTEST)=[-6,-5,-4,-3,-2,-1,0,1,2,3,4,5,-8,-7,6,7,8,9]
    integer::i,u,num
    num=NTRAIN
    if(heldout)num=NTEST
    open(newunit=u,file='runs/check.f90',status='replace')
    write(u,'(a)')'program check'
    write(u,'(a)')'  implicit none'
    write(u,'(a)')'  integer :: i, got, total'
    write(u,'(a)')'  integer, external :: solve'
    write(u,'(a,i0,a)')'  integer, parameter :: x(',num,')=[ &'
    do i=1,num
       if(i<num)then
         write(u,'(a,i0,a)')'     ',inputs(i),', &'
       else
         write(u,'(a,i0,a)')'     ',inputs(i),' ]'
       end if
    end do
    write(u,'(a,i0,a)')'  integer, parameter :: truth(',num,')=[ &'
    do i=1,num
       if(i<num)then
         write(u,'(a,i0,a)')'     ',oracle(t,inputs(i)),', &'
       else
         write(u,'(a,i0,a)')'     ',oracle(t,inputs(i)),' ]'
       end if
    end do
    write(u,'(a)')'  total=0'
    write(u,'(a,i0)')'  do i=1,',num
    write(u,'(a)')'    got=solve(x(i))'
    write(u,'(a)')'    if(got==truth(i))then'
    write(u,'(a)')'      total=total+1'
    write(u,'(a)')'    else if(total<3)then'
    write(u,'(a)')'      write(*,''(a,i0,a,i0,a,i0)'') ''FAIL input='',x(i),'' expected='',truth(i),'' got='',got'
    write(u,'(a)')'    end if'
    write(u,'(a)')'  end do'
    write(u,'(a)')'  write(*,''(a,i0)'') ''PASS_COUNT='',total'
    write(u,'(a)')'end program check'
    close(u)
  end subroutine
  subroutine print_lines(path,limit,errors_only)
    character(len=*),intent(in)::path
    integer,intent(in)::limit
    logical,intent(in)::errors_only
    character(len=500)::line
    integer::u,ios,k
    open(newunit=u,file=path,status='old',iostat=ios)
    if(ios/=0)return
    k=0
    do
      read(u,'(a)',iostat=ios)line
      if(ios/=0)exit
      if(errors_only)then
         if(index(line,'Error:')==0.and.index(line,'Fatal Error:')==0)cycle
      end if
      print '(a)','    '//trim(line)
      k=k+1
      if(k>=limit)exit
    end do
    close(u)
  end subroutine
  subroutine run_candidate(t,heldout,trace,g,passed,compiled,feedback)
    integer,intent(in)::t
    logical,intent(in)::heldout,trace
    type(program_t),intent(in)::g
    integer,intent(out)::passed,feedback
    logical,intent(out)::compiled
    integer::istat,u,ios,pos,idx
    character(len=500)::line
    passed=0;compiled=.false.;feedback=ST_SYNTAX
    do idx=1,cache_size
       if((cache_task(idx)/=t).or.(cache_heldout(idx).neqv.heldout))cycle
       if(any(cache_tokens(:,idx)/=g%tok))cycle
       passed=cache_pass(idx);compiled=cache_compiled(idx);feedback=cache_feedback(idx)
       if(trace)then
          write(*,'(a,l1,a,i0)')'  [VERIFIED CACHE] compiled=',compiled,' tests passed=',passed
       end if
       return
    end do
    call make_tests(t,heldout)
    call execute_command_line('./build-compile.sh > runs/compile.log 2>&1',exitstat=istat)
    if(istat/=0)then
       if(trace)then
          print '(a)','  [COMPILER] FAILED'
          call print_lines('runs/compile.log',2,.true.)
       end if
       call cache_result(t,heldout,g,passed,compiled,feedback)
       return
    end if
    compiled=.true.
    if(trace)print '(a)','  [COMPILER] OK'
    call execute_command_line('bash ./run-tests.sh > runs/test.log 2>&1',exitstat=istat)
    if(istat/=0)then
       feedback=ST_RUNTIME
       if(trace)then
          print '(a)','  [RUNTIME] Failed or exceeded sandbox limits'
          call print_lines('runs/test.log',2,.false.)
       end if
       call cache_result(t,heldout,g,passed,compiled,feedback)
       return
    end if
    open(newunit=u,file='runs/test.log',status='old',iostat=ios)
    if(ios/=0)then
       feedback=ST_RUNTIME;return
    end if
    do
       read(u,'(a)',iostat=ios)line
       if(ios/=0)exit
       pos=index(line,'PASS_COUNT=')
       if(pos>0)then
          read(line(pos+11:),*,iostat=ios)passed
          if(ios/=0)passed=0
       end if
    end do
    close(u)
    if(heldout)then
       if(passed==NTEST)then
          feedback=ST_BASE
       else
          feedback=ST_SEMANTIC
       end if
       if(trace)write(*,'(a,i0,a,i0)')'  [TESTS] ',passed,' / ',NTEST
    else
       if(passed==NTRAIN)then
          feedback=ST_BASE
       else
          feedback=ST_SEMANTIC
       end if
       if(trace)write(*,'(a,i0,a,i0)')'  [TESTS] ',passed,' / ',NTRAIN
    end if
    if(trace.and.feedback/=ST_BASE)call print_lines('runs/test.log',2,.false.)
    call cache_result(t,heldout,g,passed,compiled,feedback)
  end subroutine
  subroutine cache_result(t,heldout,g,passed,compiled,feedback)
    integer,intent(in)::t,passed,feedback
    logical,intent(in)::heldout,compiled
    type(program_t),intent(in)::g
    if(cache_size>=CACHE_MAX)return
    cache_size=cache_size+1
    cache_task(cache_size)=t
    cache_heldout(cache_size)=heldout
    cache_tokens(:,cache_size)=g%tok
    cache_pass(cache_size)=passed
    cache_compiled(cache_size)=compiled
    cache_feedback(cache_size)=feedback
  end subroutine
  integer function syntax_slot(g) result(slot)
    type(program_t),intent(in)::g
    integer::u,ios
    character(len=500)::line
    slot=S_OP
    open(newunit=u,file='runs/compile.log',status='old',iostat=ios)
    if(ios/=0)return
    do
      read(u,'(a)',iostat=ios)line
      if(ios/=0)exit
      if(index(line,'intent')>0.or.index(line,'declaration')>0)then
         slot=S_DECL;exit
      else if(index(line,'PROCEDURE attribute')>0.or.index(line,'LABEL attribute')>0)then
         slot=S_ASSIGN;exit
      else if(index(line,'Unexpected')>0.or.index(line,'Syntax error')>0)then
         if(g%tok(S_DECL)/=1)then
            slot=S_DECL
         else if(g%tok(S_ASSIGN)/=1)then
            slot=S_ASSIGN
         else
            slot=S_OP
         end if
         exit
      end if
    end do
    close(u)
    if(g%tok(S_DECL)/=1)slot=S_DECL
    if(g%tok(S_DECL)==1.and.g%tok(S_ASSIGN)/=1)slot=S_ASSIGN
  end function
  integer function repair_slot(t,g,feedback,tries) result(k)
    integer,intent(in)::t,feedback,tries
    type(program_t),intent(in)::g
    integer::a(NS),n,j,slot
    real(dp)::p(NM),score,best
    if(feedback==ST_SYNTAX)then
       k=syntax_slot(g);return
    end if
    if(feedback==ST_RUNTIME)then
       k=S_MODE;return
    end if
    call active_slots(g,a,n)
    ! Repair the least-confident semantic slot, rotating the alternatives
    ! so a repeatedly failing expression cannot monopolize all attempts.
    best=-1.0_dp;k=S_MODE
    do j=1,n
       slot=a(j)
       if(slot==S_DECL.or.slot==S_ASSIGN)cycle
       call probs(t,slot,ST_BASE,p)
       score=1.0_dp-p(g%tok(slot))
       if(modulo(tries+j,3)==0)score=score+0.10_dp
       if(score>best)then
          best=score;k=slot
       end if
    end do
  end function
  subroutine repair(t,g,feedback,tries,greedy,trace)
    integer,intent(in)::t,feedback,tries
    type(program_t),intent(inout)::g
    logical,intent(in)::greedy,trace
    integer::k,prev,j
    character(len=80)::before,after
    k=repair_slot(t,g,feedback,tries)
    prev=g%tok(k)
    before=token_word(k,prev)
    call sample_slot(t,g,k,feedback,greedy)
    if(g%tok(k)==prev.and.ACOUNT(k)>1)then
       ! Ensure every repair attempt actually changes one token.
       j=modulo(g%tok(k),ACOUNT(k))+1
       g%tok(k)=j
    end if
    after=token_word(k,g%tok(k))
    if(trace)then
       select case(feedback)
       case(ST_SYNTAX)
          print '(a)','  [OBSERVE] Compiler syntax/type failure'
       case(ST_SEMANTIC)
          print '(a)','  [OBSERVE] Compiles, but wrong output on tests'
       case default
          print '(a)','  [OBSERVE] Runtime or test failure'
       end select
       print '(a)','  [REPAIR] Local edit in '//trim(slot_name(k))
       print '(a)','     BEFORE: '//trim(before)
       print '(a)','     AFTER:  '//trim(after)
    end if
  end subroutine
  subroutine archive_solution(t)
    integer,intent(in)::t
    character(len=150)::cmd
    integer::rc
    write(cmd,'(a,i0,a)')'cp runs/solve.f90 results/task_',t,'_solved.f90'
    call execute_command_line(trim(cmd),exitstat=rc)
  end subroutine
  subroutine solve_episode(truth,phrase,trace,delay,success,first_intent,tries)
    integer,intent(in)::truth,phrase,delay
    logical,intent(in)::trace
    logical,intent(out)::success,first_intent
    integer,intent(out)::tries
    integer::prediction,task,passed,feedback,i,previous,repair_k
    real(dp)::confidence
    logical::compiled
    character(len=144)::prompt
    type(program_t)::g
    prompt=prompts(phrase,truth)
    call predict(prompt,prediction,confidence)
    first_intent=(prediction==truth)
    if(trace)then
       print '(a)','============================================================'
       print '(a)','[REQUEST] '//trim(prompt)
       write(*,'(a,a,a,f5.1,a)')'[LANGUAGE] ',trim(task_name(prediction)), &
          ' confidence=',confidence*100.0_dp,'%'
       print '(a)','[CURRICULUM] Labeled task: '//trim(task_name(truth))
    end if
    ! Curriculum separates code-policy learning from the language classifier.
    ! Inference/eval must use their own predicted task (no label access).
    task=truth
    call sample_program(task,g,.false.)
    success=.false.;tries=0
    do i=1,6
       tries=i
       if(trace)write(*,'(a,i0)')'[GENERATE] Attempt ',i
       call create_source(g,trace,delay)
       call run_candidate(truth,.false.,trace,g,passed,compiled,feedback)
       cumulative_attempts=cumulative_attempts+1
       if(compiled)cumulative_compiled=cumulative_compiled+1
       call reinforce_result(task,g,passed,compiled)
       if(compiled.and.passed==NTRAIN)then
          success=.true.
          call archive_solution(truth)
          if(trace)print '(a)','[VERIFIER] PASS: all training tests, accepted'
          exit
       end if
       repair_k=repair_slot(task,g,feedback,i)
       previous=g%tok(repair_k)
       call reinforce(task,repair_k,feedback,previous,-1.0_dp)
       if(i<6)call repair(task,g,feedback,i,.false.,trace)
    end do
    ! Curriculum demonstrations are learned by the token policy, not pasted
    ! into a candidate. Compiler execution supplies independent rewards.
    do i=1,3
       call teach_program(truth)
    end do
    call teach_intent(prompt,truth)
    if(trace.and..not.success)print '(a)','[VERIFIER] Attempt budget exhausted; feedback retained'
  end subroutine
  subroutine save_ckpt(path)
    character(len=*),optional,intent(in)::path
    character(len=256)::dest,tmp
    integer::u,n,rc
    integer,allocatable::seed(:)
    dest='checkpoints/latest.bvc2'
    if(present(path))dest=path
    tmp=trim(dest)//'.tmp'
    call random_seed(size=n)
    allocate(seed(n));call random_seed(get=seed)
    open(newunit=u,file=trim(tmp),access='stream',form='unformatted',status='replace')
    write(u)MAGIC,VERSION,episode,cumulative_solved,cumulative_compiled,cumulative_attempts,n
    write(u)iw,w,base,seed
    close(u)
    call execute_command_line('mv '//trim(tmp)//' '//trim(dest),exitstat=rc)
    if(rc/=0)error stop 'Cannot atomically save checkpoint'
  end subroutine
  subroutine load_ckpt(ok,path)
    logical,intent(out)::ok
    character(len=*),optional,intent(in)::path
    character(len=256)::dest
    integer::u,ios,magic,version,n,nexpected
    integer,allocatable::seed(:)
    dest='checkpoints/latest.bvc2'
    if(present(path))dest=path
    inquire(file=trim(dest),exist=ok)
    if(.not.ok)return
    open(newunit=u,file=trim(dest),access='stream',form='unformatted',status='old',iostat=ios)
    if(ios/=0)then
       ok=.false.;return
    end if
    read(u,iostat=ios)magic,version,episode,cumulative_solved,cumulative_compiled,cumulative_attempts,n
    if(ios/=0)then
       ok=.false.;close(u);return
    end if
    call random_seed(size=nexpected)
    if(magic/=MAGIC.or.version/=VERSION.or.n/=nexpected)then
       ok=.false.;close(u);return
    end if
    allocate(seed(n))
    read(u,iostat=ios)iw,w,base,seed
    close(u)
    ok=ios==0
    if(ok)call random_seed(put=seed)
  end subroutine
  subroutine append_metrics()
    integer::u,ios
    logical::exists
    inquire(file='results/metrics_v2.csv',exist=exists)
    open(newunit=u,file='results/metrics_v2.csv',status='unknown',position='append',iostat=ios)
    if(ios/=0)return
    if(.not.exists)write(u,'(a)')'episode,solved,compiled,attempts'
    write(u,'(i0,a,i0,a,i0,a,i0)')episode,',',cumulative_solved,',',cumulative_compiled,',',cumulative_attempts
    close(u)
  end subroutine
  subroutine run_train(steps,delay,verbose_every)
    integer,intent(in)::steps,delay,verbose_every
    integer::j,t,phrase,used,window_solved,window_intent
    logical::ok,good,correct
    call initialize()
    call load_ckpt(ok)
    if(ok)then
       write(*,'(a,i0)')'[RESUME] V2 checkpoint at episode ',episode
    else
       print '(a)','[INIT] New V2 token-policy: V1 checkpoints preserved separately'
    end if
    window_solved=0;window_intent=0
    do j=1,steps
       episode=episode+1
       t=modulo(episode-1,NT)+1
       phrase=modulo((episode-1)/NT,NPH-1)+1
       call solve_episode(t,phrase,mod(j-1,verbose_every)==0,delay,good,correct,used)
       if(good)then
          cumulative_solved=cumulative_solved+1;window_solved=window_solved+1
       end if
       if(correct)window_intent=window_intent+1
       if(mod(j,24)==0.or.j==steps)then
          write(*,'(a,i0,a,i0,a,i0,a,i0)')'[METRICS] episode ',episode, &
             ' solved window ',window_solved,' correct intents ',window_intent,' of ',modulo(j-1,24)+1
          window_solved=0;window_intent=0
          call save_ckpt()
          call append_metrics()
       end if
    end do
    write(*,'(a,i0)')'[DONE] V2 checkpoint saved at episode ',episode
  end subroutine
  subroutine run_eval()
    integer::t,guess,passed,feedback,solved,intents,compiled_count
    real(dp)::conf
    logical::ok,comp
    type(program_t)::g
    call initialize();call load_ckpt(ok)
    if(.not.ok)then
       print '(a)','No V2 checkpoint found.';return
    end if
    solved=0;intents=0;compiled_count=0
    do t=1,NT
       call predict(prompts(NPH,t),guess,conf)
       if(guess==t)intents=intents+1
       call sample_program(guess,g,.true.)
       call create_source(g,.false.,0)
       call run_candidate(t,.true.,.false.,g,passed,comp,feedback)
       if(comp)compiled_count=compiled_count+1
       if(comp.and.passed==NTEST)solved=solved+1
       write(*,'(a,i0,a,a,a,a,a,f5.1,a,i0,a,i0)')'task ',t,' (',trim(task_name(t)), &
            ') predicted ',trim(task_name(guess)),' confidence ',100*conf,'% tests ',passed,' / ',NTEST
    end do
    write(*,'(a,i0,a,i0,a,i0,a)')'[EVAL HELDOUT] intents ',intents,'/12, compiled ', &
       compiled_count,'/12, solved ',solved,'/12'
    print '(a)','[NOTE] Held-out phrasing and inputs; task families still overlap training.'
  end subroutine
  subroutine run_infer(prompt,delay)
    character(len=*),intent(in)::prompt
    integer,intent(in)::delay
    integer::t,tries,passed,feedback
    real(dp)::conf
    logical::ok,comp,accepted
    type(program_t)::g
    call initialize();call load_ckpt(ok)
    if(.not.ok)then
       print '(a)','No checkpoint. Train before inference.';return
    end if
    call predict(prompt,t,conf)
    write(*,'(a,a,a,f5.1,a)')'[REQUEST] '//trim(prompt)//' -> ',trim(task_name(t)), &
           ' confidence ',100*conf,'%'    if(conf<0.35_dp)then
       print '(a)','[ABSTAIN] Low confidence. Limited to 12 known integer tasks; no open-ended generation.'
       return
    end if
    call sample_program(t,g,.true.)
    accepted=.false.
    do tries=1,8
       write(*,'(a,i0)')'[GENERATE] Attempt ',tries
       call create_source(g,.true.,delay)
       ! This verification uses a test oracle for the *predicted* supported task,
       ! not access to arbitrary English semantics.
       call run_candidate(t,.true.,.true.,g,passed,comp,feedback)
       if(comp.and.passed==NTEST)then
          accepted=.true.;exit
       end if
       if(tries<8)call repair(t,g,feedback,tries,.false.,.true.)
    end do
    if(accepted)then
       print '(a)','[ACCEPTED] Predicted task passed 18 checks.'
       call archive_solution(t)
    else
       print '(a)','[UNSOLVED] Candidate did not pass within eight attempts.'
    end if
    print '(a)','[LIMITATION] This uses bounded structured token choices, not a general code LLM.'
  end subroutine
  subroutine run_selftest()
    integer::t,passed,feedback
    logical::comp,ok
    type(program_t)::g
    call initialize()
    do t=1,NT
       g=correct_program(t)
       call create_source(g,.false.,0)
       call run_candidate(t,.true.,.false.,g,passed,comp,feedback)
       if(.not.comp.or.passed/=NTEST)then
          write(*,'(a,i0,a,i0)')'FAIL: reference task ',t,' tests ',passed
          stop 1
       end if
    end do
    g=correct_program(2)
    g%tok(S_DECL)=2
    call create_source(g,.false.,0)
    call run_candidate(2,.true.,.false.,g,passed,comp,feedback)
    if(comp.or.feedback/=ST_SYNTAX)error stop 'Syntax test failed'
    g=correct_program(2)
    g%tok(S_RHS)=2
    call create_source(g,.false.,0)
    call run_candidate(2,.true.,.false.,g,passed,comp,feedback)
    if(.not.comp.or.passed==NTEST.or.feedback/=ST_SEMANTIC)error stop 'Semantic test failed'
    episode=17
    call save_ckpt('checkpoints/selftest_v2.bvc2')
    episode=0
    call load_ckpt(ok,'checkpoints/selftest_v2.bvc2')
    if(.not.ok.or.episode/=17)error stop 'Checkpoint roundtrip failed'
    print '(a)','PASS 12 reference programs (including if/loop), syntax and semantic detection, checkpoint roundtrip'
  end subroutine
  subroutine run_usage()
    print '(a)','BitVision-Code V2: native Fortran token-policy compiler-feedback experiment'
    print '(a)','  ./build/bitvision_code_v2 selftest'
    print '(a)','  ./build/bitvision_code_v2 train [episodes=240] [delay_ms=5] [verbose_every=12]'
    print '(a)','  ./build/bitvision_code_v2 eval'
    print '(a)','  ./build/bitvision_code_v2 infer "triple the integer" [delay_ms=15]'
  end subroutine
end module
program main
  use bvcode_v2
  implicit none
  character(len=30)::cmd,arg
  character(len=1200)::prompt
  integer::n,delay,v,ios
  call get_command_argument(1,cmd)
  select case(trim(cmd))
  case('selftest')
    call run_selftest()
  case('train')
    n=240;delay=5;v=12
    call get_command_argument(2,arg)
    if(len_trim(arg)>0)then
       read(arg,*,iostat=ios)n
       if(ios/=0)error stop 'Invalid episodes'
    end if
    call get_command_argument(3,arg)
    if(len_trim(arg)>0)then
       read(arg,*,iostat=ios)delay
       if(ios/=0)error stop 'Invalid delay'
    end if
    call get_command_argument(4,arg)
    if(len_trim(arg)>0)then
       read(arg,*,iostat=ios)v
       if(ios/=0)error stop 'Invalid verbosity'
    end if
    if(n<1.or.n>100000.or.delay<0.or.v<1)error stop 'Invalid training parameters'
    call run_train(n,delay,v)
  case('eval')
    call run_eval()
  case('infer')
    call get_command_argument(2,prompt)
    if(len_trim(prompt)==0)error stop 'Specify request in quotes'
    delay=15
    call get_command_argument(3,arg)
    if(len_trim(arg)>0)then
       read(arg,*,iostat=ios)delay
       if(ios/=0)error stop 'Invalid delay'
    end if
    call run_infer(trim(prompt),delay)
  case default
    call run_usage()
  end select
end program
BITVISION_V2_FORTRAN
cat > build.sh <<'BITVISION_V2_BUILD'
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p src build runs results checkpoints
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
"$FC" -O2 -std=f2008 -fcheck=all -ffree-line-length-none -Wall -Wextra src/bitvision_code_v2.f90 -o build/bitvision_code_v2
printf '[BUILD] Fortran V2 compiled with %s\n' "$FC"
BITVISION_V2_BUILD
cat > run-tests.sh <<'BITVISION_V2_TEST_RUNNER'
#!/usr/bin/env bash
set -euo pipefail
ulimit -t 3
ulimit -c 0
./runs/candidate
BITVISION_V2_TEST_RUNNER
cat > README.md <<'BITVISION_V2_README'
# BitVision-Code V2 — Native Fortran code-learning lab

This version is installed in `~/BitVision-Fortran/native_code_v2` without changing
`native_code` (V1) or `native_3d` (combat). GNU Fortran is used for the learning
policy, synthesis, compilation of sampled programs, and the test harness.

## What V2 actually implements

* 12 **closed** integer programming tasks: doubling, squaring, absolute value,
  increment, even check, sign, tripling, decrement, odd check, clamp to [-5,5],
  bounded arithmetic series, and small-input factorial.
* Independent sampled decisions for program structure, declaration, assignment,
  operands/operators, branches, and bounded loops. The compiler and test runner
  return diagnostics and observed expected/actual values.
* Localized edits for failed declarations, assignment operators, expressions,
  branches or loop actions. `[OBSERVE]`, `[REPAIR]`, and `[VERIFIER]` show
  **observable repair behavior**; these are **not internal reasoning traces**.
* Trainable hashed-character/word-feature intent classifier, categorical action
  policy, REINFORCE-style update, and supervised curriculum demonstrations.
* Live lexical-token display; adjustable inter-token delay in milliseconds.
* Deterministic task-specific compilation and test cases; **18 holdout inputs**
  for eval, 12 subset for training. Eval prompts are a sixth phrasing that does
  not occur in training. Task families are the same in training/eval.
* Checkpoint resume in `checkpoints/latest.bvc2` and CSV metrics.
* Exact candidate cache so **repeated** previously compiled/tested snippets can
  reuse results within one process. `[VERIFIED CACHE]` labels these cases.

It is **not an open-ended LLM** and cannot synthesize arbitrary Python, Rust,
Fortran applications, or evidence of emergent language reasoning. It operates
within an explicit, bounded program grammar. It does not reuse the V1 model
weights: V2 and V1 architectures differ; V1 remains untouched.

## Commands

```bash
cd ~/BitVision-Fortran/native_code_v2
./build/bitvision_code_v2 selftest
./build/bitvision_code_v2 train 240 5 1 | tee results/live-v2.log
./build/bitvision_code_v2 eval
./build/bitvision_code_v2 infer 'triple the integer' 15
```

`train [episodes] [token_delay_ms] [detailed_every]` adds new episodes to the
checkpoint. `eval` scores **one greedy generation per held-out task**, not
multi-attempt search; it will display failures even if later repair could help.

## Security boundary

The compiler receives **only snippets assembled by the allowlisted Fortran
grammar**. No user-supplied arbitrary source is inserted. Executables run as
a local process under CPU-time/core-dump limits, not a strong OS sandbox.
Do **not** extend the tool to accept and compile arbitrary internet source
without actual isolation (a separate unprivileged container or VM, filesystem
isolation, CPU/memory limits and no network).
BITVISION_V2_README
chmod +x build.sh run-tests.sh
./build.sh
./build/bitvision_code_v2 selftest
printf '\n[READY] Fortran BitVision-Code V2 installed in %s\n' "$ROOT"
printf '[NEXT] cd "%s" && ./build/bitvision_code_v2 train 240 5 1 | tee results/live-training-v2.log\n' "$ROOT"
printf '[EVAL] cd "%s" && ./build/bitvision_code_v2 eval\n' "$ROOT"