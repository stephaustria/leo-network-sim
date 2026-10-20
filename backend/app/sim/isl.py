import numpy as np

from .constants import R_EARTH


def clear_of_earth(p1: np.ndarray, p2: np.ndarray, margin_m: float) -> np.ndarray:
    """True where the segment p1-p2 stays above the Earth (plus margin)."""
    d = p2 - p1
    denom = np.einsum("ij,ij->i", d, d)
    t = -np.einsum("ij,ij->i", p1, d) / np.where(denom > 0, denom, 1.0)
    closest = p1 + np.clip(t, 0.0, 1.0)[:, None] * d
    return np.linalg.norm(closest, axis=1) > (R_EARTH + margin_m)


def greedy_match(a, b, dist, cap_a: int, cap_b: int, n_a: int, n_b: int, shared: bool) -> np.ndarray:
    """Accept candidate edges (a[k], b[k]) shortest first while both endpoints still have capacity.
    `shared` means a and b index the same set of nodes, so one degree counter is used.
    Returns the indices of the accepted edges."""
    deg_a = [0] * n_a
    deg_b = deg_a if shared else [0] * n_b
    al, bl = np.asarray(a).tolist(), np.asarray(b).tolist()
    keep = []
    for k in np.argsort(dist, kind="stable").tolist():
        i, j = al[k], bl[k]
        if deg_a[i] < cap_a and deg_b[j] < cap_b:
            deg_a[i] += 1
            deg_b[j] += 1
            keep.append(k)
    return np.array(keep, dtype=np.int64)


def _empty():
    return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)


def nearest_links(pos: np.ndarray, max_degree: int, max_range_m: float, margin_m: float):
    """Links among one set of satellites: each links to its nearest neighbours subject to range,
    line of sight and a degree cap. Returns index arrays (a, b) with a < b."""
    n = len(pos)
    if n < 2:
        return _empty()

    sq = (pos ** 2).sum(axis=1)
    d2 = sq[:, None] + sq[None, :] - 2.0 * (pos @ pos.T)
    np.fill_diagonal(d2, np.inf)

    m = min(n - 1, 2 * max_degree + 2)                         # shortlist per satellite
    near = np.argpartition(d2, m - 1, axis=1)[:, :m]
    rows = np.repeat(np.arange(n), m)
    cols = near.ravel()
    key = np.unique(np.minimum(rows, cols) * n + np.maximum(rows, cols))   # dedupe (i,j) / (j,i)
    a, b = key // n, key % n

    dist = np.sqrt(np.maximum(d2[a, b], 0.0))
    ok = dist <= max_range_m
    a, b, dist = a[ok], b[ok], dist[ok]
    ok = clear_of_earth(pos[a], pos[b], margin_m)
    a, b, dist = a[ok], b[ok], dist[ok]

    keep = greedy_match(a, b, dist, max_degree, max_degree, n, n, shared=True)
    return a[keep], b[keep]


def inter_shell_links(pos_a: np.ndarray, pos_b: np.ndarray, degree: int,
                      max_range_m: float, margin_m: float):
    """Links between two different sets of satellites, each with at most `degree` links.
    Returns index arrays (a into pos_a, b into pos_b)."""
    na, nb = len(pos_a), len(pos_b)
    if na == 0 or nb == 0 or degree <= 0:
        return _empty()

    d2 = (pos_a ** 2).sum(axis=1)[:, None] + (pos_b ** 2).sum(axis=1)[None, :] - 2.0 * (pos_a @ pos_b.T)
    m = 2 * degree + 2
    ma, mb = min(nb, m), min(na, m)
    near_b = np.argpartition(d2, ma - 1, axis=1)[:, :ma]        # for each a: its nearest b's
    near_a = np.argpartition(d2, mb - 1, axis=0)[:mb, :]        # for each b: its nearest a's
    ia = np.concatenate([np.repeat(np.arange(na), ma), near_a.ravel()])
    ib = np.concatenate([near_b.ravel(), np.tile(np.arange(nb), mb)])
    key = np.unique(ia * nb + ib)
    a, b = key // nb, key % nb

    dist = np.sqrt(np.maximum(d2[a, b], 0.0))
    ok = dist <= max_range_m
    a, b, dist = a[ok], b[ok], dist[ok]
    ok = clear_of_earth(pos_a[a], pos_b[b], margin_m)
    a, b, dist = a[ok], b[ok], dist[ok]

    keep = greedy_match(a, b, dist, degree, degree, na, nb, shared=False)
    return a[keep], b[keep]