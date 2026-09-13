clear
clc

addpath('D:\projects\efny-pipeline\scripts\neuroimaging');

% Set both roots to the dataset that should be updated before running.
bidsFolder = 'D:\BIDS_transfer\BIDS';
rawFolder = 'D:\Raw_trans';
supportedTasks = ["sst", "nback", "switch"];

assert(isfolder(bidsFolder), 'BIDS folder does not exist: %s', bidsFolder);
assert(isfolder(rawFolder), 'Raw folder does not exist: %s', rawFolder);

rawSubjectDirs = dir(rawFolder);
rawSubjectDirs = rawSubjectDirs([rawSubjectDirs.isdir]);
rawSubjectDirs(ismember({rawSubjectDirs.name}, {'.', '..'})) = [];
rawByBidsSubject = indexRawSubjects(rawSubjectDirs);

bidsSubjectDirs = dir(fullfile(bidsFolder, 'sub-THU*'));
bidsSubjectDirs = bidsSubjectDirs([bidsSubjectDirs.isdir]);
assert(~isempty(bidsSubjectDirs), ...
    'No BIDS subject folders found under %s.', bidsFolder);
[~, order] = sort(lower(string({bidsSubjectDirs.name})));
bidsSubjectDirs = bidsSubjectDirs(order);

jobs = struct('subjectPrefix', {}, 'bidsSubjectDir', {}, ...
    'psychDir', {}, 'tasks', {});
for index = 1:numel(bidsSubjectDirs)
    subjectPrefix = string(bidsSubjectDirs(index).name);
    assert(~isempty(regexp(subjectPrefix, ...
        '^sub-THU\d{12}$', 'once')), ...
        'Unexpected BIDS subject folder name: %s', subjectPrefix);

    bidsSubjectDir = fullfile( ...
        bidsSubjectDirs(index).folder, bidsSubjectDirs(index).name);
    tasks = retainedEventTasks(bidsSubjectDir, subjectPrefix, supportedTasks);
    psychDir = '';
    if ~isempty(tasks)
        assert(isKey(rawByBidsSubject, char(subjectPrefix)), ...
            'No raw subject folder maps to %s under %s.', ...
            subjectPrefix, rawFolder);
        rawSubjectDir = rawByBidsSubject(char(subjectPrefix));
        psychDir = fullfile(rawSubjectDir, 'PSYCH');
        assert(isfolder(psychDir), ...
            '%s has task BOLD data but no PSYCH folder: %s', ...
            subjectPrefix, psychDir);
    end

    jobs(end + 1, 1) = struct( ...
        'subjectPrefix', char(subjectPrefix), ...
        'bidsSubjectDir', bidsSubjectDir, ...
        'psychDir', psychDir, ...
        'tasks', tasks); %#ok<SAGROW>
end

for index = 1:numel(jobs)
    deletedCount = deleteOwnedEvents( ...
        jobs(index).bidsSubjectDir, jobs(index).subjectPrefix, ...
        supportedTasks);
    writtenTasks = write_bids_events( ...
        jobs(index).psychDir, jobs(index).bidsSubjectDir, ...
        jobs(index).subjectPrefix, jobs(index).tasks);
    fprintf('%s: deleted %d event file(s), wrote %d task(s).\n', ...
        jobs(index).subjectPrefix, deletedCount, numel(writtenTasks));
end


function rawByBidsSubject = indexRawSubjects(rawSubjectDirs)
%INDEXRAWSUBJECTS Map raw THU folder names to dated BIDS subject labels.

rawByBidsSubject = containers.Map('KeyType', 'char', 'ValueType', 'char');
for index = 1:numel(rawSubjectDirs)
    token = regexpi(rawSubjectDirs(index).name, ...
        '^THU[_-](\d{8})[_-](\d{3,4})(?:[_-].*)?$', 'tokens', 'once');
    if isempty(token)
        continue;
    end
    subjectPrefix = sprintf('sub-THU%s%04d', ...
        token{1}, str2double(token{2}));
    assert(~isKey(rawByBidsSubject, subjectPrefix), ...
        'Multiple raw subject folders map to %s.', subjectPrefix);
    rawByBidsSubject(subjectPrefix) = fullfile( ...
        rawSubjectDirs(index).folder, rawSubjectDirs(index).name);
end
end


function tasks = retainedEventTasks( ...
    bidsSubjectDir, subjectPrefix, supportedTasks)
%RETAINEDEVENTTASKS Find supported task BOLD files already present in BIDS.

funcDir = fullfile(bidsSubjectDir, 'func');
tasks = strings(0, 1);
if ~isfolder(funcDir)
    return;
end

boldFiles = [dir(fullfile(funcDir, '*_bold.nii')); ...
    dir(fullfile(funcDir, '*_bold.nii.gz'))];
for task = reshape(supportedTasks, 1, [])
    prefix = sprintf('%s_task-%s', subjectPrefix, task);
    matches = startsWith(string({boldFiles.name}), string(prefix) + "_") & ...
        endsWith(string({boldFiles.name}), ["_bold.nii", "_bold.nii.gz"]);
    assert(sum(matches) <= 1, ...
        ['%s has multiple BOLD files for task %s; one task-level event ', ...
         'file would be ambiguous.'], subjectPrefix, task);
    if any(matches)
        tasks(end + 1, 1) = task; %#ok<AGROW>
    end
end
end


function deletedCount = deleteOwnedEvents( ...
    bidsSubjectDir, subjectPrefix, supportedTasks)
%DELETEOWNEDEVENTS Delete only event files produced by this converter.

deletedCount = 0;
for task = reshape(supportedTasks, 1, [])
    eventPath = fullfile(bidsSubjectDir, 'func', ...
        sprintf('%s_task-%s_events.tsv', subjectPrefix, task));
    if isfile(eventPath)
        delete(eventPath);
        deletedCount = deletedCount + 1;
    end
end
end
