from .main import run

if __name__ == "__main__":
    report = run()
    routing = report["routing"]
    print("== Routing ==")
    print(f"routed={routing['routed']} planar_length={routing['planar_length']} "
          f"vias={routing['via_count']} weighted_total={routing['total_weighted_length']} "
          f"crossings={routing['crossings']}")
    print(f"via_validation_passed={routing['via_validation']['passed']} "
          f"errors={routing['via_validation']['errors']}")
    print("== Noise ==")
    for name, check in report["noise_spectra"]["checks"].items():
        print(name, check)
    print("Artifacts written to artifacts/: report.json, routing.svg, "
          "spectra.svg, density.svg, density_sweep.csv, density_summary.json")
