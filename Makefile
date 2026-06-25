.PHONY: setup native streamlit desktop test build

setup:
	./dev_setup.sh

native:
	./dev_run_native.sh

streamlit:
	./dev_run_streamlit.sh

desktop:
	./dev_run_desktop.sh

test:
	./dev_test.sh

build:
	./dev_build_desktop.sh
