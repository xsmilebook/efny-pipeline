clear
clc

addpath(fileparts(mfilename('fullpath')));

dcm2niix = 'D:\software\MRIcroGL_windows\MRIcroGL\Resources\dcm2niix.exe';
niftiFolder = 'D:\BIDS_transfer\NIFTI';
bidsFolder = 'D:\BIDS_transfer\BIDS';
rawFolder = 'D:\Raw_trans';
sublist = readcell('D:\BIDS_transfer\raw\sublist.txt', 'Delimiter', '');
workerCount = 4;

parfor (index = 1:numel(sublist), workerCount)
    sourceFolder = sublist{index};
    try
        dicom2bids_checked(sourceFolder, dcm2niix, ...
            niftiFolder, bidsFolder, rawFolder);
    catch exception
        warning('DICOM2BIDS:SubjectFailed', '%s failed: %s', ...
            char(string(sourceFolder)), exception.message);
    end
end
