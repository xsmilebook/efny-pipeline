% Source root follows run_dicom2bids_checked.m; set paths before running.
addpath(fileparts(mfilename('fullpath')));

rawFolder = 'D:\Raw_trans';
outputFolder = 'Z:\xuhaoshu\PSYCH_tlr';

% Omit the third argument to process all direct THU subject folders.
extract_psychopy_csv(rawFolder, outputFolder);
