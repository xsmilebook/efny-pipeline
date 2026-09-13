function writtenTasks = write_bids_events( ...
    psychDir, bidsSubjectDir, subjectPrefix, keptTasks)
%WRITE_BIDS_EVENTS Convert supported PsychoPy CSV files to BIDS events.
%
% keptTasks lists the task BOLD acquisitions retained for one participant.
% Event onsets are expressed in seconds relative to the recorded MRI trigger.

keptTasks = unique(lower(string(keptTasks)), 'stable');
supportedTasks = ["sst", "nback", "switch"];
assert(all(ismember(keptTasks, supportedTasks)), ...
    'Unsupported event task requested for %s: %s', ...
    subjectPrefix, strjoin(cellstr(keptTasks), ', '));

writtenTasks = strings(0, 1);
if isempty(keptTasks)
    return;
end
if ~isfolder(psychDir)
    warning('%s has task BOLD data but no PSYCH folder.', subjectPrefix);
    return;
end

csvFiles = dir(fullfile(psychDir, '*.csv'));
for task = reshape(keptTasks, 1, [])
    matches = false(size(csvFiles));
    for index = 1:numel(csvFiles)
        matches(index) = strcmp( ...
            classify_psychopy_task(csvFiles(index).name), task);
    end
    if ~any(matches)
        warning('%s has no event CSV file for task %s.', subjectPrefix, task);
        continue;
    end

    csvPath = '';
    try
        csvFile = chooseLatestEventCsv( ...
            csvFiles(matches), subjectPrefix, task);
        csvPath = fullfile(csvFile.folder, csvFile.name);
        events = buildEventsTable(csvPath, task);
        outputPath = fullfile(bidsSubjectDir, 'func', ...
            sprintf('%s_task-%s_events.tsv', subjectPrefix, task));
        writetable(events, outputPath, 'FileType', 'text', 'Delimiter', '\t');
        writtenTasks(end + 1, 1) = task; %#ok<AGROW>
    catch exception
        if isempty(csvPath)
            sourceDescription = strjoin({csvFiles(matches).name}, ' | ');
        else
            sourceDescription = csvPath;
        end
        warning('DICOM2BIDS:EventWriteFailed', ...
            '%s skipped events for task %s from %s: %s', ...
            subjectPrefix, task, sourceDescription, exception.message);
    end
end
end


function csvFile = chooseLatestEventCsv(csvFiles, subjectPrefix, task)
%CHOOSELATESTEVENTCSV Select the latest timestamp encoded in the filename.

if isscalar(csvFiles)
    csvFile = csvFiles;
    return;
end

timeKeys = nan(numel(csvFiles), 1);
for index = 1:numel(csvFiles)
    timeKeys(index) = eventFileTimeKey(csvFiles(index).name);
end
assert(all(isfinite(timeKeys)), ...
    ['%s has multiple event CSV files for task %s, but at least one ', ...
     'filename has no recognized timestamp.'], subjectPrefix, task);

latest = find(timeKeys == max(timeKeys));
assert(isscalar(latest), ...
    '%s has event CSV files with the same latest timestamp for task %s.', ...
    subjectPrefix, task);
csvFile = csvFiles(latest);
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
