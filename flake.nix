{
  description = "The berbl Python library";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.overlays.url = "github:dpaetzel/overlays";

  outputs = { self, nixpkgs, overlays }:

    with import nixpkgs {
      system = "x86_64-linux";
      overlays = with overlays.overlays; [ mlflow ];
    };
    let python = python39;
    in rec {
      defaultPackage.x86_64-linux = python.pkgs.buildPythonPackage rec {
        pname = "berbl";
        version = "0.1.0";

        src = self;

        # We use pyproject.toml.
        format = "pyproject";

        propagatedBuildInputs = with python.pkgs; [
          deap
          mlflow
          numpy
          numpydoc
          pandas
          scipy
          scikitlearn
          sphinx
        ];

        testInputs = with python.pkgs; [ hypothesis pytest ];

        doCheck = false;

        meta = with lib; {
          description =
            "Implementation of a Bayesian Learning Classifier System";
          license = licenses.gpl3;
        };
      };

      devShell.x86_64-linux = mkShell {
        packages = [ defaultPackage.x86_64-linux python.pkgs.tox ]
          ++ defaultPackage.x86_64-linux.testInputs;
      };
    };
}
