"""Run all cave-generation experiments and refresh artifacts/*.csv."""
from experiments import exp1_frequency, exp2_threshold, exp3_multilayer, exp4_depth


def main():
    rows1 = exp1_frequency.run()
    print(f"exp1 frequency sweep : {len(rows1)} rows -> artifacts/exp1_frequency.csv")
    rows2 = exp2_threshold.run()
    print(f"exp2 threshold sweep : {len(rows2)} rows -> artifacts/exp2_threshold.csv")
    rows3 = exp3_multilayer.run()
    print(f"exp3 multi-layer     : {len(rows3)} rows -> artifacts/exp3_multilayer.csv")
    stats4 = exp4_depth.run()
    print(f"exp4 depth interp    : {stats4['pixels_covered']} px, "
          f"max rel err {stats4['fixed_max_rel_err_vs_float']:.2e}, "
          f"consistent={stats4['consistent_rel_1e-3']}")


if __name__ == "__main__":
    main()
