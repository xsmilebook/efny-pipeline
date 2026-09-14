function psychopy2bids_checked(rawFolder, bidsFolder, sublistPath)
%PSYCHOPY2BIDS_CHECKED Build a BIDS events-only replacement dataset.
%
% rawFolder contains one source folder per participant, each with a PSYCH
% directory. sublistPath lists those source folder names. bidsFolder receives
% dataset_description.json and sub-*/func/*_events.tsv/.json files. Existing
% event files with the same BIDS names are overwritten.

rawFolder = char(string(rawFolder));
bidsFolder = char(string(bidsFolder));
sublistPath = char(string(sublistPath));

sublist = strip(string(readcell(sublistPath, 'Delimiter', '')));
sublist(ismissing(sublist) | strlength(sublist) == 0) = [];
assert(~isempty(sublist), 'No source folders listed in %s', sublistPath);

if ~isfolder(bidsFolder)
    mkdir(bidsFolder);
end
writeDatasetDescription(bidsFolder);

for index = 1:numel(sublist)
    sourceFolderName = char(sublist(index));
    try
        convertPsychopySubject(sourceFolderName, rawFolder, bidsFolder);
    catch exception
        warning('PSYCHOPY2BIDS:SubjectFailed', '%s failed: %s', ...
            sourceFolderName, exception.message);
    end
end
end


function convertPsychopySubject(sourceFolderName, rawFolder, bidsFolder)
%CONVERTPSYCHOPYSUBJECT Convert supported task CSV files for one participant.

subjectParts = regexpi(sourceFolderName, ...
    '^THU[_-](\d{8})[_-](\d{3,4})(?:[_-].*)?$', 'tokens', 'once');
assert(~isempty(subjectParts), ...
    'Unexpected subject folder name: %s', sourceFolderName);
subjectPrefix = sprintf('sub-THU%s%04d', ...
    subjectParts{1}, str2double(subjectParts{2}));

psychDir = fullfile(rawFolder, sourceFolderName, 'PSYCH');
if ~isfolder(psychDir)
    warning('PSYCHOPY2BIDS:MissingPsychFolder', ...
        '%s has no PSYCH folder: %s', subjectPrefix, psychDir);
    return;
end

csvFiles = dir(fullfile(psychDir, '*.csv'));
supportedTasks = ["sst", "nback", "switch"];
writtenCount = 0;

for task = supportedTasks
    matches = false(size(csvFiles));
    for index = 1:numel(csvFiles)
        matches(index) = strcmp( ...
            classifyPsychTask(csvFiles(index).name), task);
    end
    if ~any(matches)
        warning('PSYCHOPY2BIDS:MissingTaskCsv', ...
            '%s has no event CSV file for task %s.', subjectPrefix, task);
        continue;
    end

    csvPath = '';
    try
        csvFile = chooseEventCsv(csvFiles(matches), subjectPrefix, task);
        csvPath = fullfile(csvFile.folder, csvFile.name);
        events = buildEventsTable(csvPath, task);
        events = prepareEventsForBids(events, csvPath);

        funcDir = fullfile(bidsFolder, subjectPrefix, 'func');
        if ~isfolder(funcDir)
            mkdir(funcDir);
        end
        stem = sprintf('%s_task-%s_events', subjectPrefix, task);
        outputPath = fullfile(funcDir, [stem, '.tsv']);
        writetable(events, outputPath, ...
            'FileType', 'text', 'Delimiter', '\t');
        writeJson(eventMetadata(task), fullfile(funcDir, [stem, '.json']));
        writtenCount = writtenCount + 1;
    catch exception
        if isempty(csvPath)
            sourceDescription = strjoin({csvFiles(matches).name}, ' | ');
        else
            sourceDescription = csvPath;
        end
        warning('PSYCHOPY2BIDS:EventWriteFailed', ...
            '%s skipped events for task %s from %s: %s', ...
            subjectPrefix, task, sourceDescription, exception.message);
    end
end

fprintf('%s wrote %d task event files.\n', subjectPrefix, writtenCount);
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


function csvFile = chooseEventCsv(csvFiles, subjectPrefix, task)
%CHOOSEEVENTCSV Prefer the most data rows, then the latest filename time.

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
    ['%s has multiple event CSV files with %d data rows for task %s, ', ...
     'but at least one filename has no recognized timestamp.'], ...
    subjectPrefix, rowCounts(longest(1)), task);

latest = find(timeKeys == max(timeKeys));
assert(isscalar(latest), ...
    ['%s has event CSV files with %d data rows and the same latest ', ...
     'timestamp for task %s.'], ...
    subjectPrefix, rowCounts(longest(1)), task);
csvFile = csvFiles(longest(latest));
end


function key = eventFileTimeKey(fileName)
%EVENTFILETIMEKEY Parse PsychoPy timestamps with optional milliseconds.

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


function events = buildEventsTable(csvPath, task)
%BUILDEVENTSTABLE Convert one PsychoPy task CSV to BIDS event timing.
%
% Event onsets are seconds relative to the first recorded MRI trigger.

psych = readtable(csvPath, 'VariableNamingRule', 'preserve');
columns = eventColumnNames(psych, task, csvPath);
mriStarted = psych.(columns.mriStarted);
mriRt = psych.(columns.mriRt);
mriStartTime = mriStarted(1) + mriRt(1);
trialFixStarted = psych.(columns.trialFixStarted);
psych(isnan(trialFixStarted), :) = [];
rowCount = height(psych);

events = table('Size', [rowCount, 5], ...
    'VariableTypes', {'double', 'double', 'string', 'double', 'double'}, ...
    'VariableNames', {'onset', 'duration', 'trial_type', ...
    'response_time', 'value'});
trialFixStarted = psych.(columns.trialFixStarted);
events.onset = trialFixStarted - mriStartTime;
events.duration = psych.(columns.keyRespStopped) - trialFixStarted;
events.response_time = psych.(columns.keyRespRt);
events.value = psych.(columns.keyRespCorr);

switch task
    case "sst"
        events.trial_type(:) = "stop";
        events.trial_type(strcmp( ...
            string(psych.(columns.bad)), 'None')) = "go";
    case "nback"
        events.trial_type(:) = "2back";
        events.trial_type(contains( ...
            string(psych.(columns.trialLoopList)), '0back')) = "0back";
    case "switch"
        events.trial_type(:) = "switch";
        events.trial_type(contains( ...
            string(psych.(columns.trialLoopList)), ...
            'nonswitch')) = "nonswitch";
end
end


function events = prepareEventsForBids(events, csvPath)
%PREPAREEVENTSFORBIDS Enforce event invariants and encode missing values.

assert(all(isfinite(events.onset)), ...
    'Non-finite event onset in %s', csvPath);
assert(all((isfinite(events.duration) & events.duration >= 0) | ...
    isnan(events.duration)), ...
    'Invalid event duration in %s', csvPath);
assert(~any(ismissing(events.trial_type)), ...
    'Missing trial_type in %s', csvPath);
assert(all(isfinite(events.response_time) | isnan(events.response_time)), ...
    'Infinite response_time in %s', csvPath);
assert(all(isfinite(events.value) | isnan(events.value)), ...
    'Infinite response value in %s', csvPath);

events.duration = numericToBidsText(events.duration);
events.response_time = numericToBidsText(events.response_time);
events.value = numericToBidsText(events.value);
end


function text = numericToBidsText(values)
%NUMERICTOBIDSTEXT Encode missing numeric values with the BIDS n/a marker.

text = string(compose('%.15g', values));
text(isnan(values)) = "n/a";
end


function columns = eventColumnNames(inputTable, task, csvPath)
%EVENTCOLUMNNAMES Resolve the documented PsychoPy columns for one task.

columns = struct( ...
    'mriStarted', requiredColumnName(inputTable, ...
        ["MRI_Signal_s.started", "MRI_Signal_s_started"], csvPath), ...
    'mriRt', requiredColumnName(inputTable, ...
        ["MRI_Signal_s.rt", "MRI_Signal_s_rt"], csvPath), ...
    'trialFixStarted', requiredColumnName(inputTable, ...
        ["Trial_fix.started", "Trial_fix_started"], csvPath), ...
    'keyRespStopped', requiredColumnName(inputTable, ...
        ["key_resp.stopped", "key_resp_stopped"], csvPath), ...
    'keyRespRt', requiredColumnName(inputTable, ...
        ["key_resp.rt", "key_resp_rt"], csvPath), ...
    'keyRespCorr', requiredColumnName(inputTable, ...
        ["key_resp.corr", "key_resp_corr"], csvPath), ...
    'bad', '', ...
    'trialLoopList', '');

switch task
    case "sst"
        columns.bad = requiredColumnName(inputTable, "bad", csvPath);
    case {"nback", "switch"}
        columns.trialLoopList = requiredColumnName( ...
            inputTable, "Trial_loop_list", csvPath);
end
end


function columnName = requiredColumnName(inputTable, acceptedNames, csvPath)
%REQUIREDCOLUMNNAME Match one required raw header and reject ambiguity.

names = string(inputTable.Properties.VariableNames);
normalized = lower(strtrim(erase(names, char(65279))));
acceptedNames = string(acceptedNames);
acceptedNormalized = lower(strtrim(erase(acceptedNames, char(65279))));
matches = find(ismember(normalized, acceptedNormalized));
assert(isscalar(matches), ...
    ['Expected exactly one of [%s] in %s; actual PsychoPy headers: ', ...
     '%s'], strjoin(cellstr(acceptedNames), ' | '), csvPath, ...
    strjoin(cellstr(names), ', '));
columnName = char(names(matches));
end


function metadata = eventMetadata(task)
%EVENTMETADATA Describe generated event columns and PsychoPy provenance.

metadata = struct;
metadata.onset = struct( ...
    'Description', ...
    'Trial fixation onset relative to the first recorded MRI trigger.', ...
    'Units', 's');
metadata.duration = struct( ...
    'Description', ...
    'Time from trial fixation onset until the response component stopped.', ...
    'Units', 's');
metadata.trial_type = struct( ...
    'Description', trialTypeDescription(task));
metadata.response_time = struct( ...
    'Description', 'Response time recorded by the PsychoPy key response.', ...
    'Units', 's');
metadata.value = struct( ...
    'Description', 'Response accuracy: 1 for correct and 0 for incorrect.');
metadata.StimulusPresentation = struct( ...
    'SoftwareName', 'PsychoPy', ...
    'SoftwareRRID', 'RRID:SCR_006571');
end


function description = trialTypeDescription(task)
switch task
    case "sst"
        description = 'Stop-signal task trial: go or stop.';
    case "nback"
        description = 'N-back task condition: 0back or 2back.';
    case "switch"
        description = 'Task-switching condition: nonswitch or switch.';
end
end


function writeDatasetDescription(bidsFolder)
%WRITEDATASETDESCRIPTION Write the required BIDS root metadata.

metadata = struct( ...
    'Name', 'EFNY PsychoPy events replacement', ...
    'BIDSVersion', '1.10.0', ...
    'DatasetType', 'raw', ...
    'GeneratedBy', {{struct( ...
        'Name', 'psychopy2bids_checked.m', ...
        'Version', '1.0')}});
writeJson(metadata, fullfile(bidsFolder, 'dataset_description.json'));
end


function writeJson(metadata, path)
encoded = jsonencode(metadata, 'PrettyPrint', true);
fileId = fopen(path, 'w', 'n', 'UTF-8');
assert(fileId ~= -1, 'Cannot open JSON output: %s', path);
cleanup = onCleanup(@() fclose(fileId));
fprintf(fileId, '%s\n', encoded);
end
