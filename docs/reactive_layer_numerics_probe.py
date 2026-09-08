"""1-D reactive layer, fully implicit coupled transport + kinetic sorption.

probe4 proved the operator-split scheme diverges under refinement: with
rho_b*Kd/theta ~ 6000 the sorption substep drains the porewater every step and
the front becomes noise. Mass was conserved to 1e-14 throughout, which is the
lesson: conservation alone does not validate a scheme.

Here the sorption is solved IMPLICITLY together with transport, so there is no
splitting error. For one cell, eliminating q^{n+1} analytically:

    q^{n+1} = (q^n + dt k q_eq^{n+1}) / (1 + dt k)

so the mass exchanged with the solid over the step is linear in C^{n+1}:

    unsaturated (q_eq = Kd C):  rho_b (q^{n+1}-q^n)/dt = A C^{n+1} - B
        A = rho_b k Kd / (1 + dt k),  B = rho_b k q^n / (1 + dt k)
    saturated  (q_eq = q_max):  rho_b (q^{n+1}-q^n)/dt = -Dsat
        Dsat = rho_b k (q_max - q^n) / (1 + dt k)

which is just a diagonal term and a source in the tridiagonal system.
Governing equation, per element:

    theta dC/dt = -dJ/dz - rho_b dq/dt ,   J = v C - theta D_eff dC/dz
"""

import time

import numpy as np
from scipy.linalg import solve_banded

L, nz = 0.010, 40
dz = L / nz
theta, rho_b = 0.5, 400.0
D_eff, v, k_film = 2.0e-10, 3.0e-8, 5.0e-7
C_sed, C_water = 1.0e-3, 0.0
Kd, q_max, k_rate = 5.0, 1.0e-3, 4.0e-4

J_bare = (v + k_film) * (C_sed - C_water)
capacity = rho_b * L * q_max
kd_diff = theta * D_eff / dz**2
g_top = 1.0 / (dz / (2.0 * theta * D_eff) + 1.0 / k_film)


def solve_step(C, q, dt, picard=2):
    """One fully implicit step. Returns (C_new, q_new, j_in, j_out, clip_kg)."""
    C_guess = C.copy()
    for _ in range(picard):
        saturated = (Kd * C_guess) >= q_max
        A = np.where(saturated, 0.0, rho_b * k_rate * Kd / (1.0 + dt * k_rate))
        B = np.where(
            saturated,
            -rho_b * k_rate * (q_max - q) / (1.0 + dt * k_rate),
            rho_b * k_rate * q / (1.0 + dt * k_rate),
        )

        ab = np.zeros((3, nz))
        ab[0, 1:] = -kd_diff                       # upper: C_{i+1}
        ab[2, :-1] = -(kd_diff + v / dz)           # lower: C_{i-1}
        ab[1, :] = theta / dt + A + 2.0 * kd_diff + v / dz
        rhs = theta / dt * C + B

        # sediment face: Dirichlet at half a cell, advective inflow
        ab[1, 0] = theta / dt + A[0] + kd_diff + 2.0 * kd_diff + v / dz
        rhs[0] += (2.0 * kd_diff + v / dz) * C_sed
        # water face: advection out plus the benthic film in series
        ab[1, -1] = theta / dt + A[-1] + kd_diff + v / dz + g_top / dz
        rhs[-1] += g_top / dz * C_water

        C_new = solve_banded((1, 1), ab, rhs)
        C_guess = C_new

    q_eq = np.minimum(Kd * C_new, q_max)
    q_new = (q + dt * k_rate * q_eq) / (1.0 + dt * k_rate)
    over = q_new > q_max
    clip_kg = 0.0
    if np.any(over):
        excess = q_new[over] - q_max
        q_new[over] = q_max
        C_new[over] += rho_b * excess / theta      # mass returned, not destroyed
        clip_kg = float(np.sum(rho_b * excess) * dz)

    j_in = v * C_sed + 2.0 * theta * D_eff * (C_sed - C_new[0]) / dz
    j_out = v * C_new[-1] + g_top * (C_new[-1] - C_water)
    return C_new, q_new, j_in, j_out, clip_kg


def run(dt, years=8.0, samples=(1, 2, 3, 4, 5, 6, 7, 8)):
    n_steps = int(years * 365.25 * 86400 / dt)
    C = np.zeros(nz)
    q = np.zeros(nz)
    cum_in = cum_out = clip_total = 0.0
    out, bt5 = {}, None
    prev, max_drop = 0.0, 0.0
    t0 = time.perf_counter()
    for n in range(n_steps):
        C, q, j_in, j_out, clip = solve_step(C, q, dt)
        cum_in += j_in * dt
        cum_out += j_out * dt
        clip_total += clip
        ratio = j_out / J_bare
        max_drop = max(max_drop, prev - ratio)
        prev = ratio
        if bt5 is None and ratio > 0.05:
            bt5 = (n + 1) * dt / 86400 / 365.25
        t_yr = (n + 1) * dt / 86400 / 365.25
        for s in samples:
            if s not in out and t_yr >= s:
                out[s] = ratio
    elapsed = time.perf_counter() - t0
    stored = float(np.sum(theta * C + rho_b * q) * dz)
    residual = cum_in - cum_out - stored
    return out, bt5, max_drop, abs(residual) / max(cum_in, 1e-30), stored, elapsed, clip_total


print("fully implicit coupled scheme: dt refinement")
print(f"{'dt (h)':>7} {'bt5 (yr)':>9} {'max back step':>14} {'mass rel err':>13} "
      f"{'load %':>8} {'s':>7}   J_out/J_bare at 1..8 yr")
for dt_h in (12.0, 6.0, 3.0, 1.0, 0.5):
    dt = dt_h * 3600.0
    out, bt5, drop, rel, stored, secs, clip = run(dt)
    samples = " ".join(f"{out[k]:.4f}" for k in sorted(out))
    bt = "  n/a " if bt5 is None else f"{bt5:9.3f}"
    print(f"{dt_h:7.2f} {bt} {drop:14.2e} {rel:13.2e} "
          f"{stored/capacity*100:8.1f} {secs:7.2f}   {samples}")

print()
print("Convergence means: breakthrough time, loading and the attenuation curve")
print("stop moving as dt shrinks, and the curve is monotonic while loading.")
