clear
clc

addpath(fileparts(mfilename('fullpath')));

operation = "convert"; % "convert" or "events"
dcm2niix = 'D:\software\MRIcroGL_windows\MRIcroGL\Resources\dcm2niix.exe';
niftiFolder = 'D:\BIDS_transfer\NIFTI';
bidsFolder = 'D:\BIDS_transfer\BIDS';
rawFolder = 'D:\Raw_trans';
sublistFile = 'D:\BIDS_transfer\raw\sublist.txt';
workerCount = 4;

assert(isfolder(rawFolder), 'Raw folder does not exist: %s', rawFolder);
switch operation
    case "convert"
        sublist = readcell(sublistFile, 'Delimiter', '');
    case "events"
        assert(isfolder(bidsFolder), ...
            'BIDS folder does not exist: %s', bidsFolder);
        sublist = eventRebuildSubjectList(bidsFolder, rawFolder);
    otherwise
        error('Operation must be "convert" or "events".');
end

parfor (index = 1:numel(sublist), workerCount)
    sourceFolder = sublist{index};
    try
        dicom2bids_checked(sourceFolder, dcm2niix, ...
            niftiFolder, bidsFolder, rawFolder, operation);
    catch exception
        warning('DICOM2BIDS:SubjectFailed', '%s failed: %s', ...
            char(string(sourceFolder)), exception.message);
    end
end


function sublist = eventRebuildSubjectList(bidsFolder, rawFolder)
%EVENTREBUILDSUBJECTLIST Match every BIDS subject to one raw subject folder.

rawSubjectDirs = dir(rawFolder);
rawSubjectDirs = rawSubjectDirs([rawSubjectDirs.isdir]);
rawSubjectDirs(ismember({rawSubjectDirs.name}, {'.', '..'})) = [];
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
    rawByBidsSubject(subjectPrefix) = rawSubjectDirs(index).name;
end

bidsSubjectDirs = dir(fullfile(bidsFolder, 'sub-THU*'));
bidsSubjectDirs = bidsSubjectDirs([bidsSubjectDirs.isdir]);
assert(~isempty(bidsSubjectDirs), ...
    'No BIDS subject folders found under %s.', bidsFolder);
[~, order] = sort(lower(string({bidsSubjectDirs.name})));
bidsSubjectDirs = bidsSubjectDirs(order);

sublist = cell(numel(bidsSubjectDirs), 1);
for index = 1:numel(bidsSubjectDirs)
    subjectPrefix = bidsSubjectDirs(index).name;
    assert(~isempty(regexp(subjectPrefix, ...
        '^sub-THU\d{12}$', 'once')), ...
        'Unexpected BIDS subject folder name: %s', subjectPrefix);
    assert(isKey(rawByBidsSubject, subjectPrefix), ...
        'No raw subject folder maps to %s under %s.', ...
        subjectPrefix, rawFolder);
    sublist{index} = rawByBidsSubject(subjectPrefix);
end
end
