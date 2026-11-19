.PHONY: bench test

bench:
	python3 -m shader_permutations --runs 3

test:
	python3 -m unittest discover -v
