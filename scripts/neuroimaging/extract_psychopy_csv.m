function selection = extract_psychopy_csv(rawFolder, outputFolder, sublistPath)
%EXTRACT_PSYCHOPY_CSV Copy one original CSV per subject and supported task.
% rawFolder contains subject/PSYCH folders. Copies in outputFolder retain
% subject folders and original filenames. Optional sublistPath
% lists source subject folders; otherwise all THU subject folders are used.
% Selection matches the BIDS converters: most readtable rows, then latest
% filename timestamp. This does not match behavior to a particular BOLD run.

if nargin < 3
    sublistPath = '';
end
rawFolder = char(string(rawFolder));
outputFolder = char(string(outputFolder));
subjectPattern = '^THU[_-](\d{8})[_-](\d{3,4})(?:[_-].*)?$';
if strlength(string(sublistPath)) == 0
    folders = dir(rawFolder);
    names = string({folders([folders.isdir]).name});
    sublist = names(~cellfun(@isempty, regexpi(cellstr(names), subjectPattern)));
else
    sublist = strip(string(readcell(sublistPath, 'Delimiter', '')));
    sublist(ismissing(sublist) | strlength(sublist) == 0) = [];
end
assert(~isempty(sublist), 'No subject folders selected from %s', rawFolder);
assert(numel(unique(sublist)) == numel(sublist), ...
    'Duplicate subject folders in the extraction list.');

tasks = ["sst", "nback", "switch"];
record = struct('subject', '', 'task', '', 'status', '', ...
    'candidates', {{}}, 'candidate_rows', [], 'selected_file', '', ...
    'destination', '');
selection = repmat(record, 0, 1);

% Resolve the whole selection before copying, so ambiguity leaves no output.
for index = 1:numel(sublist)
    subject = char(sublist(index));
    assert(~isempty(regexpi(subject, subjectPattern, 'once')), ...
        'Unexpected subject folder name: %s', subject);
    psychDir = fullfile(rawFolder, subject, 'PSYCH');
    assert(isfolder(psychDir), 'Missing PSYCH folder: %s', psychDir);
    csvFiles = dir(fullfile(psychDir, '*.csv'));
    fileTasks = strings(size(csvFiles));
    for fileIndex = 1:numel(csvFiles)
        fileTasks(fileIndex) = classifyPsychTask(csvFiles(fileIndex).name);
    end

    for task = tasks
        entry = record;
        entry.subject = subject;
        entry.task = char(task);
        candidates = csvFiles(fileTasks == task);
        entry.candidates = arrayfun(@(file) fullfile(file.folder, file.name), ...
            candidates, 'UniformOutput', false);
        if isempty(candidates)
            entry.status = 'missing_task_csv';
            warning('PSYCHOPY:MissingTaskCsv', ...
                '%s has no recognized CSV for task %s.', subject, task);
        else
            [chosen, rowCounts] = chooseEventCsv(candidates, subject, task);
            entry.status = 'selected';
            entry.candidate_rows = rowCounts;
            entry.selected_file = fullfile(chosen.folder, chosen.name);
            entry.destination = fullfile(outputFolder, subject, 'PSYCH', chosen.name);
        end
        selection(end + 1, 1) = entry; %#ok<AGROW>
    end

    % Old filenames could otherwise masquerade as additional selected runs.
    existing = dir(fullfile(outputFolder, subject, 'PSYCH', '*.csv'));
    existingPaths = string(arrayfun(@(file) fullfile(file.folder, file.name), ...
        existing, 'UniformOutput', false));
    subjectEntries = selection(strcmp({selection.subject}, subject));
    assert(all(ismember(existingPaths, string({subjectEntries.destination}))), ...
        'PSYCHOPY:StaleDestinationCsv', ...
        ['Destination PSYCH contains CSV files outside the current selection ', ...
         'for %s. Use a new output root; no old files have been removed.'], subject);
end

selected = strcmp({selection.status}, 'selected');
assert(any(selected), 'No supported task CSV files selected.');
if ~isfolder(outputFolder)
    mkdir(outputFolder);
end
for index = reshape(find(selected), 1, [])
    entry = selection(index);
    destinationDir = fileparts(entry.destination);
    if ~isfolder(destinationDir)
        mkdir(destinationDir);
    end
    [success, message] = copyfile(entry.selected_file, entry.destination);
    assert(success, 'Failed to copy %s: %s', entry.selected_file, message);
end

manifest = struct('created_at', char(datetime('now', ...
    'Format', 'yyyy-MM-dd HH:mm:ss')), 'matlab_version', version, ...
    'raw_folder', rawFolder, 'output_folder', outputFolder, ...
    'sublist_path', char(string(sublistPath)), 'selection', selection);
fid = fopen(fullfile(outputFolder, 'selection_log.json'), 'w', 'n', 'UTF-8');
assert(fid ~= -1, 'Cannot write the extraction selection log.');
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%s\n', jsonencode(manifest, 'PrettyPrint', true));
fprintf('Copied %d CSV files from %d subjects to %s\n', ...
    nnz(selected), numel(sublist), outputFolder);
end


function task = classifyPsychTask(fileName)
%CLASSIFYPSYCHTASK Identify one underscore-delimited supported task token.

tokens = regexpi(char(string(fileName)), ...
    '(?<=_)(sst|nback|switch)(?=_)', 'tokens');
matchedTasks = string(cellfun(@(token) lower(token{1}), tokens, ...
    'UniformOutput', false));
matchedTasks = unique(matchedTasks, 'stable');

if isscalar(matchedTasks)
    task = matchedTasks;
else
    task = "";
end
end


function [csvFile, rowCounts] = chooseEventCsv(csvFiles, subjectPrefix, task)
%CHOOSEEVENTCSV Prefer the most data rows, then the latest filename time.

rowCounts = [];
if isscalar(csvFiles)
    csvFile = csvFiles;
    return;
end

rowCounts = zeros(numel(csvFiles), 1);
for index = 1:numel(csvFiles)
    csvPath = fullfile(csvFiles(index).folder, csvFiles(index).name);
    inputTable = readtable(csvPath, 'VariableNamingRule', 'preserve');
    rowCounts(index) = height(inputTable);
end
longest = find(rowCounts == max(rowCounts));
if isscalar(longest)
    csvFile = csvFiles(longest);
    return;
end

timeKeys = nan(numel(longest), 1);
for index = 1:numel(longest)
    timeKeys(index) = eventFileTimeKey(csvFiles(longest(index)).name);
end
assert(all(isfinite(timeKeys)), ...
    'PSYCHOPY:MissingTimestamp', ...
    ['%s has multiple event CSV files with %d data rows for task %s, ', ...
     'but at least one filename has no recognized timestamp.'], ...
    subjectPrefix, rowCounts(longest(1)), task);

latest = find(timeKeys == max(timeKeys));
assert(isscalar(latest), ...
    'PSYCHOPY:AmbiguousTimestamp', ...
    ['%s has event CSV files with %d data rows and the same latest ', ...
     'timestamp for task %s.'], ...
    subjectPrefix, rowCounts(longest(1)), task);
csvFile = csvFiles(longest(latest));
end


function key = eventFileTimeKey(fileName)
%EVENTFILETIMEKEY Parse PsychoPy timestamps with optional milliseconds.
% Preserve the converter's expression: MATLAB omits its nested millisecond
% token, so filenames differing only in milliseconds remain tied.

token = regexp(fileName, ...
    ['(\d{4}-\d{2}-\d{2})_(\d{2})h(\d{2})\.(\d{2})', ...
     '(?:\.(\d{3}))?'], 'tokens', 'once');
if isempty(token)
    key = NaN;
    return;
end

milliseconds = '000';
if numel(token) == 5 && ~isempty(token{5})
    milliseconds = token{5};
end
timestamp = sprintf('%s %s:%s:%s.%s', ...
    token{1}, token{2}, token{3}, token{4}, milliseconds);
value = datetime(timestamp, 'InputFormat', 'yyyy-MM-dd HH:mm:ss.SSS');
key = posixtime(value);
end
