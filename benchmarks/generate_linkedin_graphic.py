# ============================================================================
# HEXA-60 CORE™ — High-Throughput Base60 Encoding Engine
# Copyright (c) 2026 Ladislav Müller (IČO: 40189589). All rights reserved.
#
# PROPRIETARY AND CONFIDENTIAL SOFTWARE.
# Unauthorized copying, distribution, or modification of this file, via any
# medium, is strictly prohibited under applicable copyright laws and B2B EULA.
# ============================================================================

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

# Set dark theme & canvas (16:9 LinkedIn optimized ratio, 2100x1181)
plt.style.use('dark_background')
fig = plt.figure(figsize=(14, 7.875), dpi=150)
fig.patch.set_facecolor('#070B14')

# Layout grid with clean vertical clearances
gs = fig.add_gridspec(
    2, 2,
    width_ratios=[1.22, 1],
    height_ratios=[1, 1],
    left=0.06, right=0.94,
    top=0.78, bottom=0.09,
    wspace=0.22, hspace=0.28
)

# Header Section (Crisp, modern branding)
fig.text(0.06, 0.935, 'HEXA-60 CORE™', fontsize=23, fontweight='bold', color='#00E5FF')
fig.text(0.30, 0.940, '|   Performance Benchmark: Pure Python vs C++20 Ultra', fontsize=13.5, color='#94A3B8')
fig.text(0.06, 0.880, 'Deterministic, Identifier-Safe Base60 Binary-to-Text Encoding Engine', fontsize=11, color='#64748B')

# --- SUBPLOT 1: THROUGHPUT BAR CHART (Left column) ---
ax1 = fig.add_subplot(gs[:, 0])
ax1.set_facecolor('#0E172A')

sizes = ['16 B', '256 B', '1 KB', '4 KB', '16 KB']
x = np.arange(len(sizes))
width = 0.36

python_mb = [2.3, 2.7, 2.7, 2.7, 2.7]
cpp_mb = [22.9, 213.3, 365.7, 499.5, 544.3]
speedups = ['10.1×', '78.1×', '135.9×', '185.9×', '204.7×']

rects1 = ax1.bar(x - width/2, python_mb, width, label='Pure Python 3.14 (Reference)', color='#F43F5E', alpha=0.85, edgecolor='#FB7185', linewidth=1.2)
rects2 = ax1.bar(x + width/2, cpp_mb, width, label='C++20 Native Accelerator (nanobind)', color='#00E5FF', alpha=0.9, edgecolor='#38BDF8', linewidth=1.4)

ax1.set_title('Encoding Throughput (MB/s) by Payload Size', fontsize=12.5, fontweight='bold', color='#F1F5F9', pad=12)
ax1.set_xticks(x)
ax1.set_xticklabels(sizes, fontsize=11, color='#E2E8F0', fontweight='bold')
ax1.set_ylabel('Throughput (MB/s)', fontsize=11, color='#94A3B8')
ax1.set_ylim(0, 620)
ax1.grid(axis='y', linestyle='--', alpha=0.18, color='#64748B')
ax1.legend(loc='upper left', frameon=True, facecolor='#1E293B', edgecolor='#334155', fontsize=9.5)

# Value & Speedup labels
for i, (p, c, sp) in enumerate(zip(python_mb, cpp_mb, speedups)):
    ax1.annotate(f'{c:.1f}', (x[i] + width/2, c + 8), ha='center', va='bottom', fontsize=9, fontweight='bold', color='#38BDF8')
    if c > 80:
        ax1.annotate(sp, (x[i] + width/2, c * 0.5), ha='center', va='center', fontsize=10.5, fontweight='bold', color='#070B14')
    else:
        ax1.annotate(sp, (x[i] + width/2, c + 35), ha='center', va='center', fontsize=9.5, fontweight='bold', color='#00F5D4')

for spine in ax1.spines.values():
    spine.set_color('#334155')

# --- SUBPLOT 2 (Top Right): HERO METRICS CARD ---
ax2 = fig.add_subplot(gs[0, 1])
ax2.set_facecolor('#0E172A')
ax2.axis('off')

# Hero Card Box
card = patches.FancyBboxPatch((0.02, 0.05), 0.96, 0.90, boxstyle='round,pad=0.03,rounding_size=0.06', facecolor='#111D36', edgecolor='#00E5FF', linewidth=1.8)
ax2.add_patch(card)

ax2.text(0.5, 0.74, 'PEAK ACCELERATION', ha='center', va='center', fontsize=11, fontweight='bold', color='#38BDF8')
ax2.text(0.5, 0.44, '205×', ha='center', va='center', fontsize=48, fontweight='bold', color='#00F5D4')
ax2.text(0.5, 0.18, '544.3 MB/s (C++20)  vs  2.7 MB/s (Python)', ha='center', va='center', fontsize=11, color='#F8FAFC', fontweight='bold')

# --- SUBPLOT 3 (Bottom Right): TERMINAL OUTPUT CARD ---
ax3 = fig.add_subplot(gs[1, 1])
ax3.set_facecolor('#050811')
ax3.axis('off')

term_box = patches.FancyBboxPatch((0.02, 0.05), 0.96, 0.90, boxstyle='round,pad=0.03,rounding_size=0.06', facecolor='#050B14', edgecolor='#1E293B', linewidth=1.2)
ax3.add_patch(term_box)

# Terminal title bar controls
ax3.add_patch(patches.Circle((0.07, 0.85), 0.022, color='#EF4444'))
ax3.add_patch(patches.Circle((0.12, 0.85), 0.022, color='#F59E0B'))
ax3.add_patch(patches.Circle((0.17, 0.85), 0.022, color='#10B981'))
ax3.text(0.23, 0.85, 'terminal — benchmark.py --native', fontsize=9, color='#64748B', va='center', fontfamily='monospace')

terminal_text = (
    "$ python benchmark.py --compare\n"
    "[+] Native accelerator (nanobind) vs pure Python:\n"
    "    bytes   nat enc MB/s   pure enc MB/s   speedup\n"
    "       16        22.9 MB/s       2.3 MB/s     10.1x\n"
    "      256       213.3 MB/s       2.7 MB/s     78.1x\n"
    "     1024       365.7 MB/s       2.7 MB/s    135.9x\n"
    "     4096       499.5 MB/s       2.7 MB/s    185.9x\n"
    "    16384       544.3 MB/s       2.7 MB/s    204.7x [~205x]"
)

ax3.text(0.06, 0.40, terminal_text, fontsize=8.2, color='#6EE7B7', va='center', fontfamily='monospace', linespacing=1.28)

# Footer
fig.text(0.06, 0.03, '>> Ready for High-Throughput Microservices, IPC, and Streaming Pipelines', fontsize=9.5, color='#64748B')
fig.text(0.94, 0.03, '© 2026 Ladislav Müller | HEXA-60 CORE™', ha='right', fontsize=9.5, color='#475569')

output_path = 'HEXA60_LinkedIn_Benchmark.png'
plt.savefig(output_path, dpi=150, facecolor=fig.get_facecolor(), bbox_inches='tight')
print(f'Graphic generated successfully: {output_path}')
