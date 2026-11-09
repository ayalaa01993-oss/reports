import cv2
import numpy as np


def _group(indices: np.ndarray, gap: int = 6) -> list[int]:
    """Group adjacent indices and return the mean of each group."""
    groups: list[list[int]] = []
    for i in indices:
        if groups and i - groups[-1][-1] <= gap:
            groups[-1].append(int(i))
        else:
            groups.append([int(i)])
    return [int(np.mean(g)) for g in groups]


def find_horizontal_lines(gray: np.ndarray) -> list[int]:
    """Return the y positions of all horizontal lines on the page."""
    bw = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15
    )
    width = bw.shape[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(width // 12, 20), 1))
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel)
    profile = horiz.sum(axis=1) / 255
    return _group(np.where(profile > width * 0.12)[0])


def _dedupe(lines: list[int], med: float) -> list[int]:
    """Drop duplicate lines (too close to the previous one), e.g. from a skewed scan."""
    out = [lines[0]]
    for y in lines[1:]:
        if y - out[-1] >= 0.5 * med:
            out.append(y)
    return out


def select_table_lines(lines: list[int]) -> list[int]:
    """Select the table row lines:
    1. Remove duplicate lines.
    2. Find the longest run of evenly spaced lines.
    3. Keep going forward even if a line is missing (double gap), filling it in."""
    if len(lines) < 3:
        return lines
    med = float(np.median(np.diff(lines)))
    lines = _dedupe(lines, med)
    med = float(np.median(np.diff(lines)))

    ok = lambda d: 0.6 * med <= d <= 1.5 * med
    best: list[int] = []
    cur = [lines[0]]
    best_end = 0
    for i in range(1, len(lines)):
        if ok(lines[i] - lines[i - 1]):
            cur.append(lines[i])
        else:
            cur = [lines[i]]
        if len(cur) > len(best):
            best, best_end = list(cur), i

    # Extend forward: a gap of 2x or 3x the pitch means the scan missed a line
    for y in lines[best_end + 1:]:
        gap = y - best[-1]
        if ok(gap):
            best.append(y)
            continue
        k = round(gap / med)
        if k >= 2 and abs(gap - k * med) <= 0.25 * med:
            step = gap / k
            best.extend(int(best[-1] + step * j) for j in range(1, k))
            best.append(y)
        else:
            break
    return best