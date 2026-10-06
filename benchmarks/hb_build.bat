call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cl /nologo /std:c++20 /O2 /EHsc /Ic:\BASE60\cpp\include c:\BASE60\benchmarks\hexa60_bench.cpp /Fec:\BASE60\benchmarks\hexa60_bench.exe /Foc:\BASE60\benchmarks\hexa60_bench.obj > c:\BASE60\benchmarks\hexa60_bench_build.log 2>&1
