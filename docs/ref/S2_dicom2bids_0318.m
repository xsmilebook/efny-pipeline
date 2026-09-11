clear
clc
addpath('D:\BIDS_transfer\code');
dcm2niix='D:\software\MRIcroGL_windows\MRIcroGL\Resources\dcm2niix.exe';
% define data folder
NIFTIFolder='D:\BIDS_transfer\NIFTI';
BIDSFolder='D:\BIDS_transfer\BIDS';
RawFolder='D:\Raw_trans';

% sublist=readcell("C:\Users\Administrator\Desktop\BIDS_2nd_traTHUnsfer\raw2\sublist.txt")
% sublist=readcell([RawFolder, '\sublist.txt'], 'Delimiter', '');
sublist=readcell('D:\BIDS_transfer\raw\sublist.txt', 'Delimiter', '');
% path = fullfile(RawFolder,'/sublist.txt');
% sublist = dir(path);
for i=1:length(sublist)
    subid=sublist{i};
    dicom2bids0318(subid, dcm2niix, NIFTIFolder, BIDSFolder, RawFolder);
end
