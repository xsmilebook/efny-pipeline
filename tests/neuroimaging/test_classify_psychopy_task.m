function tests = test_classify_psychopy_task
tests = functiontests(localfunctions);
end


function setupOnce(testCase)
repoRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
scriptDir = fullfile(repoRoot, 'scripts', 'neuroimaging');
addpath(scriptDir);
testCase.TestData.scriptDir = scriptDir;
end


function teardownOnce(testCase)
rmpath(testCase.TestData.scriptDir);
end


function testStandardTaskFiles(testCase)
files = [ ...
    "THU_20231230_160_DHL_SST_2023-12-30_11h46.49.669.csv", ...
    "THU_20231230_160_DHL_nback_2023-12-30_11h30.41.503.csv", ...
    "THU_20231230_160_DHL_switch_2023-12-30_11h54.08.580.csv"];
expected = ["sst", "nback", "switch"];

verifyEqual(testCase, classifyAll(files), expected);
end


function testMixedFilesRemainDistinct(testCase)
files = [ ...
    "THU_20240121_188_ZWK_switch_2024-01-21_15h22.25.477.csv", ...
    "THU_20250724_680_LXY_SST_0702_2025-07-24_10h30.22.388.csv", ...
    "THU_20250807_703_WYH_nback_2025-08-07_16h32.05.csv", ...
    "unrelated_notes.csv"];
expected = ["switch", "sst", "nback", ""];

verifyEqual(testCase, classifyAll(files), expected);
end


function testAmbiguousTaskTokensAreRejected(testCase)
fileName = "THU_20240121_188_ZWK_sst_nback_2024-01-21.csv";

verifyEqual(testCase, classify_psychopy_task(fileName), "");
end


function tasks = classifyAll(files)
tasks = strings(size(files));
for index = 1:numel(files)
    tasks(index) = classify_psychopy_task(files(index));
end
end
