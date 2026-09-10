function dicom2bids_checked(sourceFolderName, dcm2niix, ...
    niftiFolder, bidsFolder, rawFolder)
%DICOM2BIDS_CHECKED Convert one participant after explicit series selection.
%
% All source scan containers are merged into one BIDS session. Source scan
% identity is retained internally for rescan selection and fieldmap linkage.

sourceFolderName = char(string(sourceFolderName));
subjectParts = regexpi(sourceFolderName, ...
    '^THU[_-](\d{8})[_-](\d{3,4})(?:[_-].*)?$', 'tokens', 'once');
assert(~isempty(subjectParts), ...
    'Unexpected subject folder name: %s', sourceFolderName);
subjectPrefix = sprintf('sub-THU%s%04d', ...
    subjectParts{1}, str2double(subjectParts{2}));

subjectRawDir = fullfile(rawFolder, sourceFolderName);
dicomRoot = fullfile(subjectRawDir, 'MRIdata');
psychDir = fullfile(subjectRawDir, 'PSYCH');

assert(isfolder(dicomRoot), 'Missing MRIdata folder: %s', dicomRoot);

scanGroups = discoverScanGroups(dicomRoot);
assert(~isempty(scanGroups), ...
    'No scan container with recognized sequence folders under %s', dicomRoot);

series = inspectSeries(scanGroups);
[series, fmapPairs] = selectSeries(series, scanGroups, subjectPrefix);
series = assignBidsDestinations(series, subjectPrefix);
validateUniqueDestinations(series);

niftiSubjectDir = fullfile(niftiFolder, subjectPrefix);
bidsSubjectDir = fullfile(bidsFolder, subjectPrefix);
assert(~isfolder(niftiSubjectDir), ...
    'NIfTI subject output already exists: %s', niftiSubjectDir);
assert(~isfolder(bidsSubjectDir), ...
    'BIDS subject output already exists: %s', bidsSubjectDir);

mkdir(niftiSubjectDir);

selectedIndices = find([series.selected]);
for index = reshape(selectedIndices, 1, [])
    conversionDir = fullfile(niftiSubjectDir, ...
        sprintf('scan_%03d', series(index).scanIndex), series(index).name);
    try
        [imagePath, jsonPath, bvecPath, bvalPath] = convertOneSeries( ...
            dcm2niix, series(index).path, conversionDir);
    catch exception
        warning('DICOM2BIDS:SeriesConversionFailed', ...
            '%s skipped series %s after conversion failure: %s', ...
            subjectPrefix, series(index).path, exception.message);
        series(index).selected = false;
        continue;
    end
    series(index).convertedImage = imagePath;
    series(index).convertedJson = jsonPath;
    series(index).convertedBvec = bvecPath;
    series(index).convertedBval = bvalPath;

    if strcmp(series(index).kind, 'bold')
        convertedVolumes = niftiVolumeCount(imagePath);
        assert(convertedVolumes == series(index).fileCount, ...
            ['BOLD volume mismatch for %s: %d DICOM files but %d NIfTI ', ...
             'volumes.'], series(index).path, series(index).fileCount, ...
             convertedVolumes);
    end
end

[series, fmapPairs] = dropFailedFieldmapPairs(series, fmapPairs, subjectPrefix);
validateConvertedFieldmapPairs(series, fmapPairs);

selectedIndices = find([series.selected]);
for index = reshape(selectedIndices, 1, [])
    metadata = jsondecode(fileread(series(index).convertedJson));

    switch series(index).kind
        case 'bold'
            metadata.TaskName = series(index).taskName;
            identifiers = fmapIdentifiersForBold(fmapPairs, series(index));
            metadata = setOrRemoveField(metadata, 'B0FieldSource', identifiers);

        case 'fmap'
            pairIndex = find([fmapPairs.run] == series(index).fmapRun, 1);
            metadata.B0FieldIdentifier = fmapPairs(pairIndex).identifier;
            intendedFor = boldTargetsForPair( ...
                series, fmapPairs(pairIndex), subjectPrefix);
            metadata = setOrRemoveField(metadata, 'IntendedFor', intendedFor);

        case 'dwi_b0'
            dwiIndex = find(strcmp({series.kind}, 'dwi_main') & ...
                [series.selected], 1);
            metadata.B0FieldIdentifier = 'dwi_fmap';
            intendedFor = {};
            if ~isempty(dwiIndex)
                intendedFor = {bidsUri(subjectPrefix, ...
                    series(dwiIndex).bidsImageRelative)};
            end
            metadata = setOrRemoveField(metadata, 'IntendedFor', intendedFor);

        case 'dwi_main'
            b0Exists = any(strcmp({series.kind}, 'dwi_b0') & [series.selected]);
            if b0Exists
                metadata.B0FieldSource = 'dwi_fmap';
            else
                metadata = setOrRemoveField(metadata, 'B0FieldSource', {});
            end
    end

    destinationImage = fullfile(bidsSubjectDir, ...
        series(index).bidsImageRelative);
    destinationJson = replaceNiftiExtension(destinationImage, '.json');
    copyNoOverwrite(series(index).convertedImage, destinationImage);
    writeJson(metadata, destinationJson);

    if strcmp(series(index).kind, 'dwi_main')
        assert(isfile(series(index).convertedBvec) && ...
            isfile(series(index).convertedBval), ...
            'Missing bvec/bval for main DWI series: %s', series(index).path);
        copyNoOverwrite(series(index).convertedBvec, ...
            replaceNiftiExtension(destinationImage, '.bvec'));
        copyNoOverwrite(series(index).convertedBval, ...
            replaceNiftiExtension(destinationImage, '.bval'));
    end
end

writeEvents(psychDir, bidsSubjectDir, subjectPrefix, series);
end


function scanGroups = discoverScanGroups(dicomRoot)
%DISCOVERSCANGROUPS Find folders that directly contain recognized series.

template = struct('path', '', 'relativePath', '', 'sequenceDirs', []);
scanGroups = repmat(template, 0, 1);
scanGroups = walkForScanGroups(dicomRoot, dicomRoot, scanGroups);

[~, order] = sort(lower(string({scanGroups.relativePath})));
scanGroups = scanGroups(order);
end


function scanGroups = walkForScanGroups(currentPath, dicomRoot, scanGroups)
entries = dir(currentPath);
entries = entries([entries.isdir]);
entries(ismember({entries.name}, {'.', '..'})) = [];

[~, order] = sort(lower(string({entries.name})));
entries = entries(order);
isSequence = arrayfun(@(entry) isSequenceFolderName(entry.name), entries);

if any(isSequence)
    relativePath = erase(currentPath, [dicomRoot, filesep]);
    if isempty(relativePath)
        relativePath = '.';
    end
    record.path = currentPath;
    record.relativePath = relativePath;
    record.sequenceDirs = entries(isSequence);
    scanGroups(end + 1, 1) = record; %#ok<AGROW>
end

for index = reshape(find(~isSequence), 1, [])
    childPath = fullfile(entries(index).folder, entries(index).name);
    scanGroups = walkForScanGroups(childPath, dicomRoot, scanGroups);
end
end


function tf = isSequenceFolderName(name)
tf = ~isempty(regexpi(name, ...
    '^(EP2D_|LOCALIZER|PHOENIXZIPREPORT|SMS.*_(BOLD|DIFF)_|T1_|T2_)', ...
    'once'));
end


function series = inspectSeries(scanGroups)
%INSPECTSERIES Read one DICOM header and count files for every source series.

series = repmat(seriesTemplate(), 0, 1);

for scanIndex = 1:numel(scanGroups)
    sequenceDirs = scanGroups(scanIndex).sequenceDirs;
    for sequenceIndex = 1:numel(sequenceDirs)
        sequencePath = fullfile(sequenceDirs(sequenceIndex).folder, ...
            sequenceDirs(sequenceIndex).name);

        record = seriesTemplate();
        record.scanIndex = scanIndex;
        record.name = sequenceDirs(sequenceIndex).name;
        record.path = sequencePath;
        record = classifySeries(record);
        if strcmp(record.kind, 'ignore') || ...
                strcmp(record.kind, 'dwi_derived')
            continue;
        end

        dicomFiles = listDicomFiles(sequencePath);
        assert(~isempty(dicomFiles), ...
            'Recognized series folder has no DICOM files: %s', sequencePath);
        header = dicominfo(dicomFiles{1});

        record.fileCount = numel(dicomFiles);
        record.seriesNumber = getSeriesNumber(header, record.name);
        record.acquisitionKey = getAcquisitionKey(header, record.seriesNumber);
        if strcmp(record.kind, 't1')
            record.prescanNormalized = hasPrescanNormalize(header);
        end
        series(end + 1, 1) = record; %#ok<AGROW>
    end
end
end


function record = seriesTemplate()
record = struct( ...
    'scanIndex', 0, ...
    'name', '', ...
    'path', '', ...
    'fileCount', 0, ...
    'seriesNumber', NaN, ...
    'acquisitionKey', NaN, ...
    'kind', 'ignore', ...
    'logicalKey', '', ...
    'taskName', '', ...
    'restRun', NaN, ...
    'direction', '', ...
    'taskMarkedFmap', false, ...
    'prescanNormalized', false, ...
    'selected', false, ...
    'fmapRun', NaN, ...
    'bidsImageRelative', '', ...
    'convertedImage', '', ...
    'convertedJson', '', ...
    'convertedBvec', '', ...
    'convertedBval', '');
end


function record = classifySeries(record)
name = upper(record.name);

restToken = regexp(name, ...
    '^SMS.*_BOLD_REST([0-9]{1,2})_[0-9]+$', 'tokens', 'once');
taskToken = regexp(name, ...
    '^SMS.*_BOLD_(SST|NBACK|SWITCH)_[0-9]+$', 'tokens', 'once');

if ~isempty(restToken)
    record.kind = 'bold';
    record.restRun = str2double(restToken{1});
    record.logicalKey = sprintf('rest_%d', record.restRun);
    record.taskName = 'rest';
elseif ~isempty(taskToken)
    record.kind = 'bold';
    record.taskName = lower(taskToken{1});
    record.logicalKey = record.taskName;
elseif ~isempty(regexp(name, '^EP2D_.*SE_2MM.*_[0-9]+$', 'once'))
    record.kind = 'fmap';
    record.taskMarkedFmap = contains(name, '_TASK');
    if contains(name, '_AP')
        record.direction = 'AP';
    elseif contains(name, '_PA')
        record.direction = 'PA';
    else
        error('Cannot determine fieldmap direction: %s', record.path);
    end
elseif ~isempty(regexp(name, ...
        '^SMS.*_DIFF_CMR130_B0_AP_[0-9]+$', 'once'))
    record.kind = 'dwi_b0';
elseif ~isempty(regexp(name, ...
        '^SMS.*_DIFF_CMR130_PA_[0-9]+$', 'once'))
    record.kind = 'dwi_main';
elseif contains(name, '_DIFF_') && any(contains(name, ...
        {'_ADC_', '_FA_', '_COLFA_', '_TENSOR_', '_TRACEW_'}))
    record.kind = 'dwi_derived';
elseif ~isempty(regexp(name, '^T1_MPRAGE.*_[0-9]+$', 'once'))
    record.kind = 't1';
elseif ~isempty(regexp(name, '^T2_SPC.*_[0-9]+$', 'once'))
    record.kind = 't2';
end
end


function [series, fmapPairs] = selectSeries(series, scanGroups, subjectPrefix)
%SELECTSERIES Resolve BOLD/T1 duplicates and complete fieldmap pairs.

series = selectBoldSeries(series, subjectPrefix);
series = selectT1Series(series, subjectPrefix);
series = selectLongestLatestSeries(series, 't2', subjectPrefix);
series = selectDwiSeries(series, subjectPrefix);
[series, fmapPairs] = selectFieldmapPairs(series, scanGroups, subjectPrefix);
end


function series = selectBoldSeries(series, subjectPrefix)
boldIndices = find(strcmp({series.kind}, 'bold'));
logicalKeys = unique(string({series(boldIndices).logicalKey}), 'stable');

for key = reshape(logicalKeys, 1, [])
    indices = boldIndices(strcmp({series(boldIndices).logicalKey}, key));
    isRest = startsWith(key, 'rest_');

    if isRest
        complete = [series(indices).fileCount] == 180;
        if any(complete)
            candidateIndices = indices(complete);
        else
            warning('DICOM2BIDS:IncompleteRest', ...
                ['%s has no 180-volume candidate for %s; retaining the ', ...
                 'latest available run.'], subjectPrefix, key);
            candidateIndices = indices;
        end
    else
        maximumFrames = max([series(indices).fileCount]);
        complete = [series(indices).fileCount] == maximumFrames;
        candidateIndices = indices(complete);
    end

    chosen = chooseLatestSeries(series, candidateIndices, ...
        sprintf('%s %s', subjectPrefix, key));
    series(chosen).selected = true;
end
end


function series = selectT1Series(series, subjectPrefix)
t1Indices = find(strcmp({series.kind}, 't1'));
if isempty(t1Indices)
    return;
end

normalized = t1Indices([series(t1Indices).prescanNormalized]);
assert(~isempty(normalized), ...
    '%s has T1 MPRAGE data but no Prescan Normalize reconstruction.', ...
    subjectPrefix);
series = selectLongestLatestSeries( ...
    series, 't1', subjectPrefix, normalized);
end


function series = selectLongestLatestSeries(series, kind, subjectPrefix, indices)
%SELECTLONGESTLATESTSERIES Prefer file count, then acquisition time.

if nargin < 4
    indices = find(strcmp({series.kind}, kind));
end
if isempty(indices)
    return;
end

maximumFiles = max([series(indices).fileCount]);
longest = indices([series(indices).fileCount] == maximumFiles);
chosen = chooseLatestSeries(series, longest, ...
    sprintf('%s %s', subjectPrefix, kind));
series(chosen).selected = true;
end


function series = selectDwiSeries(series, subjectPrefix)
mainMask = strcmp({series.kind}, 'dwi_main');
b0Mask = strcmp({series.kind}, 'dwi_b0');

if ~any(mainMask)
    assert(~any(b0Mask), ...
        '%s has a DWI B0 AP series but no main DWI.', subjectPrefix);
    return;
end

series = selectLongestLatestSeries(series, 'dwi_main', subjectPrefix);
mainIndex = find(mainMask & [series.selected], 1);

sameScanMask = b0Mask & ...
    [series.scanIndex] == series(mainIndex).scanIndex;
assert(any(sameScanMask), ...
    '%s selected main DWI has no DWI B0 AP series in the same scan: %s', ...
    subjectPrefix, series(mainIndex).path);
series = selectLongestLatestSeries( ...
    series, 'dwi_b0', subjectPrefix, find(sameScanMask));
end


function [series, pairs] = selectFieldmapPairs(series, scanGroups, subjectPrefix)
pairTemplate = struct('scanIndex', 0, 'apSeriesIndex', 0, ...
    'paSeriesIndex', 0, 'acquisitionKey', NaN, 'run', 0, ...
    'identifier', '', 'boldScope', 'all');
pairs = repmat(pairTemplate, 0, 1);

for scanIndex = 1:numel(scanGroups)
    indices = find(strcmp({series.kind}, 'fmap') & ...
        [series.scanIndex] == scanIndex);
    if isempty(indices)
        continue;
    end

    taskMarked = [series(indices).taskMarkedFmap];
    maximumFiles = max([series(indices).fileCount]);
    [regularPairs, regularComplete] = completeFieldmapPairs( ...
        series, indices(~taskMarked), scanIndex, maximumFiles, pairTemplate);
    [taskPairs, taskComplete] = completeFieldmapPairs( ...
        series, indices(taskMarked), scanIndex, maximumFiles, pairTemplate);

    if regularComplete && taskComplete
        [regularPairs.boldScope] = deal('rest');
        [taskPairs.boldScope] = deal('task');
        scanPairs = [regularPairs; taskPairs];
    elseif regularComplete
        scanPairs = regularPairs;
        if any(taskMarked)
            warning('DICOM2BIDS:IncompleteTaskFieldmap', ...
                ['%s ignored incomplete _TASK fieldmaps and retained the ', ...
                 'regular fieldmap for all BOLD runs: %s'], ...
                subjectPrefix, scanGroups(scanIndex).relativePath);
        end
    elseif taskComplete
        scanPairs = taskPairs;
        if any(~taskMarked)
            warning('DICOM2BIDS:IncompleteRegularFieldmap', ...
                ['%s ignored incomplete regular fieldmaps and retained the ', ...
                 '_TASK fieldmap for all BOLD runs: %s'], ...
                subjectPrefix, scanGroups(scanIndex).relativePath);
        end
    else
        warning('DICOM2BIDS:NoCompleteFieldmap', ...
            ['%s has no balanced complete AP/PA fieldmap pair; fieldmaps ', ...
             'will be omitted: %s'], ...
            subjectPrefix, scanGroups(scanIndex).relativePath);
        continue;
    end
    pairs = [pairs; scanPairs]; %#ok<AGROW>
end

if isempty(pairs)
    return;
end

sortMatrix = [[pairs.acquisitionKey]', ...
    [series([pairs.apSeriesIndex]).seriesNumber]'];
[~, order] = sortrows(sortMatrix, [1, 2]);
pairs = pairs(order);

for run = 1:numel(pairs)
    pairs(run).run = run;
    pairs(run).identifier = sprintf('func_fmap_run_%d', run);
    selected = [pairs(run).apSeriesIndex, pairs(run).paSeriesIndex];
    for index = selected
        series(index).selected = true;
        series(index).fmapRun = run;
    end
end
end


function [pairs, isComplete] = completeFieldmapPairs( ...
    series, indices, scanIndex, requiredFileCount, pairTemplate)
%COMPLETEFIELDMAPPAIRS Retain balanced AP/PA pairs at the largest file count.

pairs = repmat(pairTemplate, 0, 1);
isComplete = false;
if isempty(indices)
    return;
end

completeIndices = indices([series(indices).fileCount] == requiredFileCount);
apIndices = completeIndices(strcmp({series(completeIndices).direction}, 'AP'));
paIndices = completeIndices(strcmp({series(completeIndices).direction}, 'PA'));
if isempty(apIndices) || numel(apIndices) ~= numel(paIndices)
    return;
end

apIndices = sortSeriesByTime(series, apIndices);
paIndices = sortSeriesByTime(series, paIndices);
for pairIndex = 1:numel(apIndices)
    pair = pairTemplate;
    pair.scanIndex = scanIndex;
    pair.apSeriesIndex = apIndices(pairIndex);
    pair.paSeriesIndex = paIndices(pairIndex);
    pair.acquisitionKey = min( ...
        series(pair.apSeriesIndex).acquisitionKey, ...
        series(pair.paSeriesIndex).acquisitionKey);
    pairs(end + 1, 1) = pair; %#ok<AGROW>
end
isComplete = true;
end


function chosen = chooseLatestSeries(series, indices, description)
if isscalar(indices)
    chosen = indices;
    return;
end

sortMatrix = [[series(indices).acquisitionKey]', ...
    [series(indices).seriesNumber]'];
[sortedValues, order] = sortrows(sortMatrix, [1, 2]);
if isequal(sortedValues(end, :), sortedValues(end - 1, :))
    error('Cannot determine the latest series for %s.', description);
end
chosen = indices(order(end));
end


function indices = sortSeriesByTime(series, indices)
sortMatrix = [[series(indices).acquisitionKey]', ...
    [series(indices).seriesNumber]'];
[~, order] = sortrows(sortMatrix, [1, 2]);
indices = indices(order);
end


function series = assignBidsDestinations(series, subjectPrefix)
for index = reshape(find([series.selected]), 1, [])
    switch series(index).kind
        case 'bold'
            if strcmp(series(index).taskName, 'rest')
                stem = sprintf('%s_task-rest_run-%d_bold', ...
                    subjectPrefix, series(index).restRun);
            else
                stem = sprintf('%s_task-%s_bold', ...
                    subjectPrefix, series(index).taskName);
            end
            series(index).bidsImageRelative = fullfile('func', [stem, '.nii.gz']);

        case 'fmap'
            stem = sprintf('%s_dir-%s_run-%d_epi', subjectPrefix, ...
                series(index).direction, series(index).fmapRun);
            series(index).bidsImageRelative = fullfile('fmap', [stem, '.nii.gz']);

        case 'dwi_main'
            series(index).bidsImageRelative = fullfile('dwi', ...
                [subjectPrefix, '_dir-PA_dwi.nii.gz']);

        case 'dwi_b0'
            series(index).bidsImageRelative = fullfile('fmap', ...
                [subjectPrefix, '_acq-dwi_dir-AP_epi.nii.gz']);

        case 't1'
            series(index).bidsImageRelative = fullfile('anat', ...
                [subjectPrefix, '_T1w.nii.gz']);

        case 't2'
            series(index).bidsImageRelative = fullfile('anat', ...
                [subjectPrefix, '_T2w.nii.gz']);
    end
end

end


function validateUniqueDestinations(series)
selected = series([series.selected]);
destinations = lower(string({selected.bidsImageRelative}));
assert(numel(destinations) == numel(unique(destinations)), ...
    'Multiple selected source series map to the same BIDS destination.');
end


function identifiers = fmapIdentifiersForBold(fmapPairs, boldSeries)
sameScan = [fmapPairs.scanIndex] == boldSeries.scanIndex;
scopes = string({fmapPairs.boldScope});
if strcmp(boldSeries.taskName, 'rest')
    matchesBold = scopes == "all" | scopes == "rest";
else
    matchesBold = scopes == "all" | scopes == "task";
end
identifiers = {fmapPairs(sameScan & matchesBold).identifier};
end


function targets = boldTargetsForPair(series, pair, subjectPrefix)
indices = find(strcmp({series.kind}, 'bold') & [series.selected] & ...
    [series.scanIndex] == pair.scanIndex);
if strcmp(pair.boldScope, 'rest')
    indices = indices(strcmp({series(indices).taskName}, 'rest'));
elseif strcmp(pair.boldScope, 'task')
    indices = indices(~strcmp({series(indices).taskName}, 'rest'));
end
targets = cell(1, numel(indices));
for item = 1:numel(indices)
    targets{item} = bidsUri(subjectPrefix, ...
        series(indices(item)).bidsImageRelative);
end
end


function [series, pairs] = dropFailedFieldmapPairs(series, pairs, subjectPrefix)
%DROPFAILEDFIELDMAPPAIRS Omit both directions when either conversion failed.

keep = true(size(pairs));
for pairIndex = 1:numel(pairs)
    pairSeries = [pairs(pairIndex).apSeriesIndex, ...
        pairs(pairIndex).paSeriesIndex];
    if ~all([series(pairSeries).selected])
        warning('DICOM2BIDS:IncompleteConvertedFieldmapPair', ...
            '%s omitted fieldmap pair %d because one direction failed.', ...
            subjectPrefix, pairIndex);
        [series(pairSeries).selected] = deal(false);
        keep(pairIndex) = false;
    end
end
pairs = pairs(keep);
end


function uri = bidsUri(subjectPrefix, relativePath)
relativePath = strrep(relativePath, '\', '/');
uri = ['bids::', subjectPrefix, '/', relativePath];
end


function files = listDicomFiles(folder)
entries = dir(folder);
entries = entries(~[entries.isdir]);
keep = false(size(entries));
for index = 1:numel(entries)
    [~, ~, extension] = fileparts(entries(index).name);
    keep(index) = isempty(extension) || ...
        any(strcmpi(extension, {'.dcm', '.ima'}));
end
entries = entries(keep);
[~, order] = sort(lower(string({entries.name})));
entries = entries(order);
files = fullfile({entries.folder}, {entries.name});
end


function number = getSeriesNumber(header, folderName)
if isfield(header, 'SeriesNumber')
    number = double(header.SeriesNumber);
    return;
end
token = regexp(folderName, '_(\d+)$', 'tokens', 'once');
assert(~isempty(token), 'Cannot determine SeriesNumber for %s', folderName);
number = str2double(token{1});
end


function key = getAcquisitionKey(header, seriesNumber)
dateText = firstMetadataText(header, ...
    {'AcquisitionDate', 'SeriesDate', 'StudyDate'});
timeText = firstMetadataText(header, ...
    {'AcquisitionTime', 'SeriesTime', 'StudyTime'});

dateDigits = regexprep(dateText, '[^0-9]', '');
if numel(dateDigits) >= 8
    dateNumber = str2double(dateDigits(1:8));
else
    dateNumber = 0;
end
timeNumber = str2double(timeText);
if isnan(timeNumber)
    timeNumber = 0;
end
key = dateNumber * 1e6 + timeNumber + seriesNumber * 1e-6;
end


function text = firstMetadataText(header, fieldNames)
text = '';
for index = 1:numel(fieldNames)
    fieldName = fieldNames{index};
    if isfield(header, fieldName)
        text = char(string(header.(fieldName)));
        if ~isempty(text)
            return;
        end
    end
end
end


function tf = hasPrescanNormalize(header)
imageTypeText = '';
if isfield(header, 'ImageType')
    imageTypeText = upper(valueToText(header.ImageType));
end
imageTypeTokens = regexp(imageTypeText, '[\\,; ]+', 'split');
tf = any(strcmp(imageTypeTokens, 'NORM'));
if tf
    return;
end

privateText = '';
fieldNames = fieldnames(header);
for index = 1:numel(fieldNames)
    fieldName = fieldNames{index};
    if startsWith(fieldName, 'Private_0029') || ...
            contains(upper(fieldName), 'CSA')
        privateText = [privateText, ' ', ...
            valueToText(header.(fieldName))]; %#ok<AGROW>
    end
end
privateText = upper(privateText);
tf = contains(privateText, 'NORMALIZEALGO') && ...
    contains(privateText, 'PRESCAN');
end


function text = valueToText(value)
if ischar(value)
    text = value;
elseif isstring(value)
    text = strjoin(cellstr(value(:)), ' ');
elseif iscell(value)
    parts = cellfun(@valueToText, value, 'UniformOutput', false);
    text = strjoin(parts, ' ');
elseif isa(value, 'uint8')
    text = char(value(:)');
else
    text = '';
end
end


function [imagePath, jsonPath, bvecPath, bvalPath] = convertOneSeries( ...
    dcm2niix, sourcePath, conversionDir)
mkdir(conversionDir);

command = sprintf('"%s" -f converted -i y -z y -w 2 -o "%s" "%s"', ...
    dcm2niix, conversionDir, sourcePath);
[status, output] = system(command);
assert(status == 0, 'dcm2niix failed for %s:\n%s', sourcePath, output);

jsonFiles = dir(fullfile(conversionDir, '*.json'));
assert(isscalar(jsonFiles), ...
    'Expected one dcm2niix JSON output for %s, found %d.', ...
    sourcePath, numel(jsonFiles));
jsonPath = fullfile(jsonFiles(1).folder, jsonFiles(1).name);
[~, baseName] = fileparts(jsonFiles(1).name);

imagePath = fullfile(conversionDir, [baseName, '.nii.gz']);
assert(isfile(imagePath), 'Missing converted NIfTI: %s', imagePath);
bvecPath = fullfile(conversionDir, [baseName, '.bvec']);
bvalPath = fullfile(conversionDir, [baseName, '.bval']);
end


function count = niftiVolumeCount(imagePath)
info = niftiinfo(imagePath);
if numel(info.ImageSize) >= 4
    count = info.ImageSize(4);
else
    count = 1;
end
end


function validateConvertedFieldmapPairs(series, fmapPairs)
%VALIDATECONVERTEDFIELDMAPPAIRS Check geometry and opposing PE directions.

for pairIndex = 1:numel(fmapPairs)
    ap = series(fmapPairs(pairIndex).apSeriesIndex);
    pa = series(fmapPairs(pairIndex).paSeriesIndex);
    apJson = jsondecode(fileread(ap.convertedJson));
    paJson = jsondecode(fileread(pa.convertedJson));

    assert(isfield(apJson, 'PhaseEncodingDirection') && ...
        isfield(paJson, 'PhaseEncodingDirection'), ...
        'Missing PhaseEncodingDirection for fieldmap run %d.', ...
        fmapPairs(pairIndex).run);
    assert(areOppositePhaseEncoding( ...
        apJson.PhaseEncodingDirection, paJson.PhaseEncodingDirection), ...
        'Fieldmap run %d does not have opposing phase-encoding directions.', ...
        fmapPairs(pairIndex).run);

    apInfo = niftiinfo(ap.convertedImage);
    paInfo = niftiinfo(pa.convertedImage);
    assert(isequal(apInfo.ImageSize, paInfo.ImageSize), ...
        'AP/PA NIfTI dimensions differ for fieldmap run %d.', ...
        fmapPairs(pairIndex).run);

    for field = {'EchoTime', 'RepetitionTime', 'TotalReadoutTime'}
        fieldName = field{1};
        if isfield(apJson, fieldName) && isfield(paJson, fieldName)
            assert(abs(double(apJson.(fieldName)) - ...
                double(paJson.(fieldName))) < 1e-9, ...
                'AP/PA %s differs for fieldmap run %d.', ...
                fieldName, fmapPairs(pairIndex).run);
        end
    end
end
end


function tf = areOppositePhaseEncoding(first, second)
first = char(string(first));
second = char(string(second));
firstAxis = erase(first, '-');
secondAxis = erase(second, '-');
firstNegative = endsWith(first, '-');
secondNegative = endsWith(second, '-');
tf = strcmp(firstAxis, secondAxis) && xor(firstNegative, secondNegative);
end


function writeJson(metadata, path)
encoded = jsonencode(metadata, 'PrettyPrint', true);
fileId = fopen(path, 'w', 'n', 'UTF-8');
assert(fileId ~= -1, 'Cannot open JSON output: %s', path);
cleanup = onCleanup(@() fclose(fileId));
fprintf(fileId, '%s\n', encoded);
end


function metadata = setOrRemoveField(metadata, fieldName, value)
if isempty(value)
    if isfield(metadata, fieldName)
        metadata = rmfield(metadata, fieldName);
    end
else
    if iscell(value) && isscalar(value)
        metadata.(fieldName) = value{1};
    else
        metadata.(fieldName) = value;
    end
end
end


function destination = replaceNiftiExtension(path, newExtension)
destination = [path(1:end - 7), newExtension];
end


function copyNoOverwrite(source, destination)
parent = fileparts(destination);
if ~isfolder(parent)
    mkdir(parent);
end
[success, message] = copyfile(source, destination);
assert(success, 'Failed to copy %s to %s: %s', source, destination, message);
end


function writeEvents(psychDir, bidsSubjectDir, subjectPrefix, series)
keptTasks = unique(string({series(strcmp({series.kind}, 'bold') & ...
    [series.selected]).taskName}));
keptTasks(keptTasks == "rest") = [];
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
        matches(index) = strcmp(classifyPsychTask(csvFiles(index).name), task);
    end
    if ~any(matches)
        warning('%s has no event CSV file for task %s.', subjectPrefix, task);
        continue;
    end
    csvFile = chooseLatestEventCsv(csvFiles(matches), subjectPrefix, task);
    events = buildEventsTable(fullfile(csvFile.folder, csvFile.name), task);
    outputPath = fullfile(bidsSubjectDir, 'func', ...
        sprintf('%s_task-%s_events.tsv', subjectPrefix, task));
    writetable(events, outputPath, 'FileType', 'text', 'Delimiter', '\t');
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
token = regexp(fileName, ...
    '(\d{4}-\d{2}-\d{2})_(\d{2})h(\d{2})\.(\d{2})\.(\d{3})', ...
    'tokens', 'once');
if isempty(token)
    key = NaN;
    return;
end

timestamp = sprintf('%s %s:%s:%s.%s', token{:});
value = datetime(timestamp, 'InputFormat', 'yyyy-MM-dd HH:mm:ss.SSS');
key = posixtime(value);
end


function task = classifyPsychTask(fileName)
tasks = ["sst", "nback", "switch"];
hits = contains(upper(string(fileName)), upper(tasks));
if sum(hits) == 1
    task = tasks(hits);
else
    task = "";
end
end


function events = buildEventsTable(csvPath, task)
psych = readtable(csvPath, 'VariableNamingRule', 'preserve');
mriStartTime = psych.MRI_Signal_s_started(1) + ...
    psych.MRI_Signal_s_rt(1);
psych(isnan(psych.Trial_fix_started), :) = [];
rowCount = height(psych);

events = table('Size', [rowCount, 5], ...
    'VariableTypes', {'double', 'double', 'string', 'double', 'double'}, ...
    'VariableNames', {'onset', 'duration', 'trial_type', ...
    'response_time', 'value'});
events.onset = psych.Trial_fix_started - mriStartTime;
events.duration = psych.key_resp_stopped - psych.Trial_fix_started;
events.response_time = psych.key_resp_rt;
events.value = psych.key_resp_corr;

switch task
    case "sst"
        badColumn = originalColumnName(psych, 'bad', csvPath);
        events.trial_type(:) = "stop";
        events.trial_type(strcmp(string(psych.(badColumn)), 'None')) = "go";
    case "nback"
        events.trial_type(:) = "2back";
        events.trial_type(contains(psych.Trial_loop_list, '0back')) = "0back";
    case "switch"
        events.trial_type(:) = "switch";
        events.trial_type(contains( ...
            psych.Trial_loop_list, 'nonswitch')) = "nonswitch";
end
end


function columnName = originalColumnName(inputTable, expectedName, csvPath)
%ORIGINALCOLUMNNAME Match a required CSV column without MATLAB renaming it.

names = string(inputTable.Properties.VariableNames);
normalized = lower(strtrim(erase(names, char(65279))));
matches = find(normalized == lower(string(expectedName)));
assert(isscalar(matches), ...
    'Expected exactly one %s column in %s; available columns: %s', ...
    expectedName, csvPath, strjoin(cellstr(names), ', '));
columnName = char(names(matches));
end
