function tests = test_dicom2bids_events
tests = functiontests(localfunctions);
end


function setupOnce(testCase)
repoRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
scriptDir = fullfile(repoRoot, 'scripts', 'neuroimaging');
addpath(scriptDir);

testRoot = tempname;
rawRoot = fullfile(testRoot, 'raw');
bidsRoot = fullfile(testRoot, 'bids');
sourceFolder = 'THU_20231230_160_DHL';
subjectPrefix = 'sub-THU202312300160';
psychDir = fullfile(rawRoot, sourceFolder, 'PSYCH');
funcDir = fullfile(bidsRoot, subjectPrefix, 'func');
mkdir(psychDir);
mkdir(funcDir);

for task = ["sst", "nback", "switch"]
    createEmptyFile(fullfile(funcDir, ...
        sprintf('%s_task-%s_bold.nii.gz', subjectPrefix, task)));
    createEmptyFile(fullfile(funcDir, ...
        sprintf('%s_task-%s_events.tsv', subjectPrefix, task)));
end
unrelatedEvent = fullfile(funcDir, ...
    sprintf('%s_task-other_events.tsv', subjectPrefix));
createEmptyFile(unrelatedEvent);

writeSstCsv(fullfile(psychDir, ...
    'THU_20231230_160_DHL_SST_0702_2023-12-30_11h46.49.669.csv'));
writeNbackCsv(fullfile(psychDir, ...
    'THU_20231230_160_DHL_nback_2023-12-30_11h30.41.csv'));
writeSwitchCsv(fullfile(psychDir, ...
    'THU_20231230_160_DHL_switch_2023-12-30_11h53.00.100.csv'), ...
    [""; "switch"; "switch"]);
writeSwitchCsv(fullfile(psychDir, ...
    'THU_20231230_160_DHL_switch_2023-12-30_11h54.08.csv'), ...
    [""; "nonswitch"; "switch"]);
writeNbackCsv(fullfile(psychDir, ...
    'THU_20231230_160_DHL_sst_nback_2023-12-30_12h00.00.csv'));

testCase.TestData.scriptDir = scriptDir;
testCase.TestData.testRoot = testRoot;
testCase.TestData.rawRoot = rawRoot;
testCase.TestData.bidsRoot = bidsRoot;
testCase.TestData.sourceFolder = sourceFolder;
testCase.TestData.subjectPrefix = subjectPrefix;
testCase.TestData.funcDir = funcDir;
testCase.TestData.unrelatedEvent = unrelatedEvent;
end


function teardownOnce(testCase)
rmpath(testCase.TestData.scriptDir);
rmdir(testCase.TestData.testRoot, 's');
end


function testMixedPsychopyTasksAreRebuilt(testCase)
dicom2bids_checked(testCase.TestData.sourceFolder, '', '', ...
    testCase.TestData.bidsRoot, testCase.TestData.rawRoot, "events");

prefix = testCase.TestData.subjectPrefix;
funcDir = testCase.TestData.funcDir;
sst = readtable(fullfile(funcDir, ...
    sprintf('%s_task-sst_events.tsv', prefix)), ...
    'FileType', 'text', 'Delimiter', '\t');
nback = readtable(fullfile(funcDir, ...
    sprintf('%s_task-nback_events.tsv', prefix)), ...
    'FileType', 'text', 'Delimiter', '\t');
taskSwitch = readtable(fullfile(funcDir, ...
    sprintf('%s_task-switch_events.tsv', prefix)), ...
    'FileType', 'text', 'Delimiter', '\t');

verifyEqual(testCase, string(sst.trial_type), ["go"; "stop"]);
verifyEqual(testCase, string(nback.trial_type), ["0back"; "2back"]);
verifyEqual(testCase, string(taskSwitch.trial_type), ...
    ["nonswitch"; "switch"]);
verifyTrue(testCase, isfile(testCase.TestData.unrelatedEvent));
end


function writeSstCsv(path)
base = basePsychopyColumns();
bad = [""; "None"; "material/Banana_1.png"];
output = addvars(base, bad, 'NewVariableNames', 'bad');
writetable(output, path);
end


function writeNbackCsv(path)
base = basePsychopyColumns();
trialLoopList = [""; "conditions/0back.xlsx"; "conditions/2back.xlsx"];
output = addvars(base, trialLoopList, ...
    'NewVariableNames', 'Trial_loop_list');
writetable(output, path);
end


function writeSwitchCsv(path, trialLoopList)
base = basePsychopyColumns();
output = addvars(base, trialLoopList, ...
    'NewVariableNames', 'Trial_loop_list');
writetable(output, path);
end


function output = basePsychopyColumns()
output = table( ...
    [0; NaN; NaN], ...
    [1; NaN; NaN], ...
    [NaN; 2; 4], ...
    [NaN; 3; 5], ...
    [NaN; 0.5; 0.6], ...
    [NaN; 1; 0], ...
    'VariableNames', { ...
    'MRI_Signal_s_started', 'MRI_Signal_s_rt', 'Trial_fix_started', ...
    'key_resp_stopped', 'key_resp_rt', 'key_resp_corr'});
end


function createEmptyFile(path)
fileId = fopen(path, 'w');
assert(fileId ~= -1, 'Cannot create test file: %s', path);
fclose(fileId);
end
