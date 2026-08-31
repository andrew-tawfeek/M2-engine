find_program(PACKAGE_BENCHMARK_PYTHON NAMES python3 REQUIRED)

add_custom_target(M2-package-gc-benchmarks
  COMMAND ${PACKAGE_BENCHMARK_PYTHON}
    ${CMAKE_CURRENT_SOURCE_DIR}/run.py
    --m2 ${M2_DIST_PREFIX}/${M2_INSTALL_BINDIR}/M2
    --output-dir ${CMAKE_BINARY_DIR}/benchmark-results/package-gc
  DEPENDS M2-core
  USES_TERMINAL
  COMMENT "Comparing package workloads with garbage collection on and off"
  VERBATIM)
