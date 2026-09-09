function run_dicom2bids_checked(sublistFile, dcm2niix, ...
    niftiFolder, bidsFolder, rawFolder)
%RUN_DICOM2BIDS_CHECKED Convert a validated subject list to one-session BIDS.

sublist = readcell(sublistFile, 'Delimiter', '');
sublist = string(sublist(:));
sublist = strip(sublist);
sublist = sublist(~ismissing(sublist) & strlength(sublist) > 0);

if numel(unique(sublist)) ~= numel(sublist)
    duplicates = unique(sublist(countEach(sublist) > 1));
    error('The subject list contains duplicate source-folder entries: %s', ...
        strjoin(duplicates, ', '));
end

labels = strings(size(sublist));
for index = 1:numel(sublist)
    labels(index) = bids_subject_label(sublist(index));
end
if numel(unique(labels)) ~= numel(labels)
    [uniqueLabels, ~, group] = unique(labels);
    counts = accumarray(group, 1);
    duplicateLabels = uniqueLabels(counts > 1);
    error('Multiple source folders map to the same BIDS subject label: %s', ...
        char(strjoin(duplicateLabels, ', ')));
end

for index = 1:numel(sublist)
    sourceFolder = char(sublist(index));
    dicom2bids_checked(sourceFolder, dcm2niix, ...
        niftiFolder, bidsFolder, rawFolder);
end
end


function counts = countEach(values)
%COUNTEACH Return the frequency of each value at its original positions.

[~, ~, group] = unique(values);
frequency = accumarray(group, 1);
counts = frequency(group);
end
