-- Run the active portion of a slow regression test in a fresh process.
slowGCName = scriptCommandLine#1;
slowGCFile = scriptCommandLine#2;
setRandomSeed 20260913;
slowGCBefore = GCstats();
slowGCTiming = elapsedTiming input slowGCFile;
slowGCAfter = GCstats();
print("M2_PACKAGE_BENCHMARK|" | slowGCName
    | "|" | toString first toSequence slowGCTiming
    | "|" | toString(slowGCAfter#"numGCs" - slowGCBefore#"numGCs")
    | "|" | toString(slowGCAfter#"bytesAlloc" - slowGCBefore#"bytesAlloc")
    | "|" | toString slowGCAfter#"heapSize"
    | "|" | toString(slowGCAfter#"gcCpuTimeSecs" - slowGCBefore#"gcCpuTimeSecs"));
print("M2_SLOW_GC_TOTAL|" | toString slowGCAfter#"numGCs");
exit 0;
