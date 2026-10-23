import numpy as np

from ffsa.data.prepare import fill_single_pits


def test_single_cell_pit_filled_but_real_depression_kept():
    z = np.full((9, 9), 10.0)
    z[2, 2] = 8.0                    # one-cell pit -> filled
    z[5:8, 5:8] = 9.0                # 3x3 depression -> kept
    z[6, 6] = 8.5
    out = fill_single_pits(z)
    assert out[2, 2] == 10.0
    assert np.all(out[5:8, 5:8] <= 9.0)
    assert out[6, 6] == 9.0          # its own centre pit is a single-cell pit within the depression
