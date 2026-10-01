import time
from base60_arithmetic import base60_add, base60_multiply, base60_fraction

lines = []

# Addition benchmark
lines.append("=== ADDITION BENCHMARK ===")
test_cases_add = [('1','1'), ('W','W'), ('100','50'), ('ZZZZ','ZZZZ')]
for a, b in test_cases_add:
    times = []
    for _ in range(1000):
        start = time.perf_counter()
        result = base60_add(a, b)
        end = time.perf_counter()
        times.append(end - start)
    avg = sum(times) / len(times)
    lines.append(f"{a}+{b}: avg {avg*1e6:.2f} us (1000 runs)")

# Multiplication benchmark
lines.append("\n=== MULTIPLICATION BENCHMARK ===")
test_cases_mul = [('2','3'), ('W','W'), ('100','50'), ('ZZ','ZZ')]
for a, b in test_cases_mul:
    times = []
    for _ in range(1000):
        start = time.perf_counter()
        result = base60_multiply(a, b)
        end = time.perf_counter()
        times.append(end - start)
    avg = sum(times) / len(times)
    lines.append(f"{a}*{b}: avg {avg*1e6:.2f} us (1000 runs)")

# Fraction benchmark
lines.append("\n=== FRACTION BENCHMARK ===")
test_cases_frac = [('1','2'), ('1','3'), ('1','4'), ('1','6')]
for num, den in test_cases_frac:
    times = []
    for _ in range(1000):
        start = time.perf_counter()
        result = base60_fraction(num, den)
        end = time.perf_counter()
        times.append(end - start)
    avg = sum(times) / len(times)
    lines.append(f"{num}/{den}: avg {avg*1e6:.2f} us (1000 runs)")

# Save to file
with open('benchmark_final.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')

print("Benchmark completed - saved to benchmark_final.txt")
