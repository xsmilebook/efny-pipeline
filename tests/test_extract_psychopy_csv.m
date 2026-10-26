function tests = test_extract_psychopy_csv
%TEST_EXTRACT_PSYCHOPY_CSV Check scientific file selection and copy boundaries.
tests = functiontests(localfunctions);
end


function setupOnce(testCase)
projectRoot = fileparts(fileparts(mfilename('fullpath')));
testCase.TestData.oldPath = path;
addpath(fullfile(projectRoot, 'scripts', 'neuroimaging'));
end


function teardownOnce(testCase)
path(testCase.TestData.oldPath);
end


function setup(testCase)
root = tempname;
subject = 'THU_20260728_1006_LWY';
psychDir = fullfile(root, 'raw', subject, 'PSYCH');
mkdir(psychDir);
testCase.TestData.root = root;
testCase.TestData.subject = subject;
testCase.TestData.outputSubject = 'sub-THU202607281006';
testCase.TestData.psychDir = psychDir;
testCase.TestData.raw = fullfile(root, 'raw');
testCase.TestData.output = fullfile(root, 'selected');
for task = ["SST", "nback", "switch"]
    name = sprintf('%s_%s_2026-07-28_13h30.00.csv', subject, task);
    writeCsv(fullfile(psychDir, name), 1);
end
end


function teardown(testCase)
rmdir(testCase.TestData.root, 's');
end


function testRowsBeforeTimeAndTimestampTie(testCase)
d = testCase.TestData;
sst = [d.subject, '_SST_2026-07-28_13h31.00.csv'];
writeCsv(fullfile(d.psychDir, sst), 4);
writeCsv(fullfile(d.psychDir, ...
    [d.subject, '_SST_2026-07-28_13h32.00.csv']), 3);
writeCsv(fullfile(d.psychDir, ...
    [d.subject, '_nback_2026-07-28_13h31.00.csv']), 3);
nback = [d.subject, '_nback_2026-07-28_13h31.01.001.csv'];
writeCsv(fullfile(d.psychDir, nback), 3);
switchFile = [d.subject, '_switch_without_time.csv'];
writeCsv(fullfile(d.psychDir, switchFile), 4);
writeCsv(fullfile(d.psychDir, 'unknown.csv'), 50);
writeCsv(fullfile(d.psychDir, [d.subject, '_SST_nback_ambiguous.csv']), 50);
writeCsv(fullfile(d.psychDir, [d.subject, '_SST_backup.log']), 50);
selection = extract_psychopy_csv(d.raw, d.output);
expected = string({sst, nback, switchFile});
destination = fullfile(d.output, d.outputSubject, 'PSYCH');
actual = dir(fullfile(destination, '*'));
verifyEqual(testCase, sort(string({actual(~[actual.isdir]).name})), sort(expected));
for name = expected
    verifyEqual(testCase, fileread(fullfile(destination, name)), ...
        fileread(fullfile(d.psychDir, name)));
end
verifyEqual(testCase, numel(selection), 3);
verifyEqual(testCase, string({selection.output_subject}), ...
    repmat(string(d.outputSubject), 1, 3));
verifyFalse(testCase, isfolder(fullfile(d.output, d.subject)));
manifest = jsondecode(fileread(fullfile(d.output, 'selection_log.json')));
verifyEqual(testCase, string({manifest.selection.status}), repmat("selected", 1, 3));
end


function testMissingTimestampTieFailsBeforeCopy(testCase)
d = testCase.TestData;
writeCsv(fullfile(d.psychDir, [d.subject, '_nback_without_time.csv']), 1);
verifyError(testCase, @() extract_psychopy_csv(d.raw, d.output), ...
    'PSYCHOPY:MissingTimestamp');
verifyFalse(testCase, isfolder(d.output));
end


function testSameSecondDifferentMillisecondsFailsBeforeCopy(testCase)
d = testCase.TestData;
writeCsv(fullfile(d.psychDir, ...
    [d.subject, '_switch_copy_2026-07-28_13h30.00.500.csv']), 1);
verifyError(testCase, @() extract_psychopy_csv(d.raw, d.output), ...
    'PSYCHOPY:AmbiguousTimestamp');
verifyFalse(testCase, isfolder(d.output));
end


function testMissingTaskIsRecorded(testCase)
d = testCase.TestData;
delete(fullfile(d.psychDir, '*_switch_*.csv'));
verifyWarning(testCase, @() extract_psychopy_csv(d.raw, d.output), ...
    'PSYCHOPY:MissingTaskCsv');
manifest = jsondecode(fileread(fullfile(d.output, 'selection_log.json')));
verifyEqual(testCase, manifest.selection(3).status, 'missing_task_csv');
end


function testExistingOutputIsPreserved(testCase)
d = testCase.TestData;
destination = fullfile(d.output, d.outputSubject, 'PSYCH');
mkdir(destination);
sentinel = fullfile(destination, 'existing.csv');
writeCsv(sentinel, 2);
before = fileread(sentinel);
verifyError(testCase, @() extract_psychopy_csv(d.raw, d.output), ...
    'PSYCHOPY:StaleDestinationCsv');
verifyEqual(testCase, fileread(sentinel), before);
end


function testMissingPsychFolderDoesNotBlockOtherSubjects(testCase)
d = testCase.TestData;
missingSubject = 'THU_20260728_1005_MISSING';
mkdir(fullfile(d.raw, missingSubject));
verifyWarning(testCase, @() extract_psychopy_csv(d.raw, d.output), ...
    'PSYCHOPY:MissingPsychFolder');
manifest = jsondecode(fileread(fullfile(d.output, 'selection_log.json')));
entries = manifest.selection;
missing = strcmp({entries.subject}, missingSubject);
verifyEqual(testCase, nnz(missing), 3);
verifyEqual(testCase, string({entries(missing).status}), ...
    repmat("missing_psych_folder", 1, 3));
verifyEqual(testCase, nnz(strcmp({entries.status}, 'selected')), 3);
files = dir(fullfile(d.output, d.outputSubject, 'PSYCH', '*.csv'));
verifyEqual(testCase, numel(files), 3);
verifyFalse(testCase, isfolder(fullfile(d.output, missingSubject)));
verifyFalse(testCase, isfolder(fullfile(d.output, 'sub-THU202607281005')));
end


function testAllMissingPsychFoldersStillWriteLog(testCase)
d = testCase.TestData;
rmdir(d.psychDir, 's');
verifyWarning(testCase, @() extract_psychopy_csv(d.raw, d.output), ...
    'PSYCHOPY:MissingPsychFolder');
manifest = jsondecode(fileread(fullfile(d.output, 'selection_log.json')));
verifyEqual(testCase, string({manifest.selection.status}), ...
    repmat("missing_psych_folder", 1, 3));
verifyFalse(testCase, isfolder(fullfile(d.output, d.subject)));
verifyFalse(testCase, isfolder(fullfile(d.output, d.outputSubject)));
end


function testSameSelectionCanBeCopiedAgain(testCase)
d = testCase.TestData;
first = extract_psychopy_csv(d.raw, d.output);
second = extract_psychopy_csv(d.raw, d.output);
verifyEqual(testCase, second, first);
files = dir(fullfile(d.output, d.outputSubject, 'PSYCH', '*.csv'));
verifyEqual(testCase, numel(files), 3);
end


function testExplicitSubjectList(testCase)
d = testCase.TestData;
mkdir(fullfile(d.raw, 'THU_20260728_1007_OTHER'));
sublist = fullfile(d.root, 'sublist.txt');
fid = fopen(sublist, 'w');
fprintf(fid, '%s\n', d.subject);
fclose(fid);
selection = extract_psychopy_csv(d.raw, d.output, sublist);
verifyEqual(testCase, string({selection.subject}), repmat(string(d.subject), 1, 3));
end


function testNoSupportedCsvDoesNotCreateSubjectFolder(testCase)
d = testCase.TestData;
delete(fullfile(d.psychDir, '*.csv'));
writeCsv(fullfile(d.psychDir, 'unknown.csv'), 2);
verifyWarning(testCase, @() extract_psychopy_csv(d.raw, d.output), ...
    'PSYCHOPY:MissingTaskCsv');
manifest = jsondecode(fileread(fullfile(d.output, 'selection_log.json')));
verifyEqual(testCase, string({manifest.selection.status}), ...
    repmat("missing_task_csv", 1, 3));
verifyFalse(testCase, isfolder(fullfile(d.output, d.outputSubject)));
verifyFalse(testCase, isfolder(fullfile(d.output, d.subject)));
end


function testThreeDigitSubjectNumberIsPadded(testCase)
d = testCase.TestData;
sourceSubject = 'THU_20260728_160_ABC';
psychDir = fullfile(d.raw, sourceSubject, 'PSYCH');
mkdir(psychDir);
for task = ["SST", "nback", "switch"]
    writeCsv(fullfile(psychDir, sprintf('%s_%s_record.csv', sourceSubject, task)), 1);
end
selection = extract_psychopy_csv(d.raw, d.output);
entries = selection(strcmp({selection.subject}, sourceSubject));
verifyEqual(testCase, string({entries.output_subject}), ...
    repmat("sub-THU202607280160", 1, 3));
verifyTrue(testCase, isfolder(fullfile(d.output, 'sub-THU202607280160', 'PSYCH')));
verifyFalse(testCase, isfolder(fullfile(d.output, sourceSubject)));
end


function testCollidingSubjectLabelsFailBeforeCopy(testCase)
d = testCase.TestData;
otherSubject = 'THU-20260728-1006-ABC';
psychDir = fullfile(d.raw, otherSubject, 'PSYCH');
mkdir(psychDir);
for task = ["SST", "nback", "switch"]
    writeCsv(fullfile(psychDir, sprintf('duplicate_%s_record.csv', task)), 1);
end
verifyError(testCase, @() extract_psychopy_csv(d.raw, d.output), ...
    'PSYCHOPY:DuplicateOutputSubject');
verifyFalse(testCase, isfolder(d.output));
end


function writeCsv(filePath, rows)
% Include missing fixation times: selection counts raw rows before filtering.
t = table((1:rows)', nan(rows, 1), ...
    'VariableNames', {'trial', 'Trial_fix.started'});
writetable(t, filePath, 'FileType', 'text', 'Delimiter', ',');
end
