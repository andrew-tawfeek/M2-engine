-- Package-level workloads for comparing normal garbage collection with
-- GC_DONT_GC=1.  Package loading happens before the timed region.

benchmarkGCWorkloadName = scriptCommandLine#1;
benchmarkGCIterations = value scriptCommandLine#2;

benchmarkGCPackages = new HashTable from {
    "graphs-edge-resolution" => "Graphs",
    "hyperplane-orlik-terao" => "HyperplaneArrangements",
    "primary-decomposition" => "PrimaryDecomposition",
    "schubert-lines" => "Schubert2",
    "simplicial-dual-resolution" => "SimplicialComplexes",
    "boij-soederberg" => "BoijSoederberg"};
if not benchmarkGCPackages#?benchmarkGCWorkloadName then
    error("unknown package benchmark: " | benchmarkGCWorkloadName);
needsPackage benchmarkGCPackages#benchmarkGCWorkloadName;

benchmarkGCGraphs = iterations -> (
    -- Derived from the completeGraph and edgeIdeal examples in Graphs.m2.
    scan(iterations, iteration -> (
        G := completeGraph 12;
        I := edgeIdeal G;
        C := res I;
        assert(numgens source gens I === 66);
        assert(C.dd_1 != 0))));

benchmarkGCHyperplaneArrangements = iterations -> (
    -- Derived from the Orlik-Terao braid arrangement example.
    scan(iterations, iteration -> (
        A := arrangement "braid";
        I := orlikTerao A;
        C := res I;
        assert(numgens source gens I > 0);
        assert(C.dd_1 != 0))));

benchmarkGCPrimaryDecomposition = iterations -> (
    -- The five-component starter example in PrimaryDecomposition/examples.m2.
    scan(iterations, iteration -> (
        R := ZZ/32003[a,b,c,d,e,f];
        I := ideal(
            a^2*c*d*f^2, b^2*c*d*f^2, a^2*b*d*f^2,
            b^3*d*f^2, a^3*d*f^2, a*b^2*d*f^2,
            a^2*c*d*e, b^2*c*d*e, a^2*b*d*e,
            b^3*d*e, a^3*d*e, a*b^2*d*e,
            a^2*c*d^2, b^2*c*d^2, a^2*b*d^2,
            b^3*d^2, a^3*d^2, a*b^2*d^2,
            a^2*c^2*f^2, b^2*c^2*f^2, a^2*b*c*f^2,
            b^3*c*f^2, a^3*c*f^2, a*b^2*c*f^2,
            a^2*b^2*f^2, b^4*f^2, a^3*b*f^2,
            a*b^3*f^2, a^4*f^2);
        components := primaryDecomposition I;
        assert(#components === 5))));

benchmarkGCSchubert2 = iterations -> (
    -- The 2,875 lines on a quintic threefold example in Schubert2/demo.m2.
    scan(iterations, iteration -> (
        point := base();
        grassmannian := flagBundle({3,2}, point);
        quotientBundle := grassmannian.Bundles#1;
        answer := integral chern symmetricPower(5, quotientBundle);
        assert(answer == 2875))));

benchmarkGCSimplicialComplexes = iterations -> (
    -- The Bayer-Charalambous-Popescu Alexander-dual example.
    scan(iterations, iteration -> (
        R := QQ[x_0 .. x_6];
        Gamma := simplicialComplex {
            x_0*x_1*x_3, x_1*x_3*x_4, x_1*x_2*x_4,
            x_2*x_4*x_5, x_2*x_3*x_5, x_3*x_5*x_6,
            x_3*x_4*x_6, x_0*x_4*x_6, x_0*x_4*x_5,
            x_0*x_1*x_5, x_1*x_5*x_6, x_1*x_2*x_6,
            x_0*x_2*x_6, x_0*x_2*x_3};
        I := ideal Gamma;
        J := ideal dual Gamma;
        RI := res I;
        RJ := res J;
        assert(pdim comodule I === regularity J);
        assert(RI.dd_1 != 0 and RJ.dd_1 != 0))));

benchmarkGCBoijSoederberg = iterations -> (
    -- The eliminateBetti complete-intersection example in BoijSoederberg.m2.
    scan(iterations, iteration -> (
        R := ZZ/8821[x,y,z,w];
        I := ideal(x,y^4,z^8,w^9);
        B := betti res I;
        X := eliminateBetti B;
        assert(X#(0,{0},0) === 12);
        assert(X#(2,{13},13) === 10))));

benchmarkGCWorkloads = new HashTable from {
    "graphs-edge-resolution" => benchmarkGCGraphs,
    "hyperplane-orlik-terao" => benchmarkGCHyperplaneArrangements,
    "primary-decomposition" => benchmarkGCPrimaryDecomposition,
    "schubert-lines" => benchmarkGCSchubert2,
    "simplicial-dual-resolution" => benchmarkGCSimplicialComplexes,
    "boij-soederberg" => benchmarkGCBoijSoederberg};

benchmarkGCWorkload = benchmarkGCWorkloads#benchmarkGCWorkloadName;
benchmarkGCWorkload 0;
benchmarkGCBefore = GCstats();
benchmarkGCTime = elapsedTiming benchmarkGCWorkload benchmarkGCIterations;
benchmarkGCAfter = GCstats();
benchmarkGCElapsed = first toSequence benchmarkGCTime;

print("M2_PACKAGE_BENCHMARK"
    | "|" | benchmarkGCWorkloadName
    | "|" | toString benchmarkGCElapsed
    | "|" | toString(benchmarkGCAfter#"numGCs" - benchmarkGCBefore#"numGCs")
    | "|" | toString(benchmarkGCAfter#"bytesAlloc" - benchmarkGCBefore#"bytesAlloc")
    | "|" | toString benchmarkGCAfter#"heapSize"
    | "|" | toString(benchmarkGCAfter#"gcCpuTimeSecs" - benchmarkGCBefore#"gcCpuTimeSecs"));

exit 0;
