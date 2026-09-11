function dicom2bids0318(subid, dcm2niix, NIFTIFolder, BIDSFolder, RawFolder)
dicomFolder = fullfile(RawFolder, subid, 'MRIdata');
PSYCHpath = fullfile(RawFolder, subid, 'PSYCH');

%% step 1: make nifiti dir
idx_spec = strfind(subid, '_');
idx_length = 1:length(subid);
idx_length(idx_spec) = [];
subj = subid(idx_length);
nifti_subj_dir = fullfile(NIFTIFolder, ['sub-', subj]);
if ~exist(nifti_subj_dir, 'dir'), mkdir(nifti_subj_dir); end

%% step 2: convert dicom to nifti (SESSION-AWARE + folder-based naming)

% session folders = direct children under MRIdata
sess = dir(dicomFolder);
sess = sess([sess.isdir]);
sess(ismember({sess.name},{'.','..'})) = [];

for si = 1:numel(sess)
    sessName = sess(si).name;
    sessPath = fullfile(sess(si).folder, sessName);

    % make nifti session dir
    nifti_sess_dir = fullfile(nifti_subj_dir, sessName);
    if ~exist(nifti_sess_dir, 'dir'), mkdir(nifti_sess_dir); end

    % find leaf folders with dicoms under this session
    allDirs = dir(fullfile(sessPath, '**'));
    allDirs = allDirs([allDirs.isdir]);
    allDirs(ismember({allDirs.name},{'.','..'})) = [];

    seriesFolders = {};
    for k = 1:numel(allDirs)
        p = fullfile(allDirs(k).folder, allDirs(k).name);

        hasDcm = ~isempty(dir(fullfile(p, '*.dcm')));
        hasIMA = ~isempty(dir(fullfile(p, '*.IMA')));
        hasNoExt = ~isempty(dir(fullfile(p, '*'))) && any(arrayfun(@(x) isempty(fileparts(x.name)), dir(fullfile(p,'*'))));

        if hasDcm || hasIMA || hasNoExt
            seriesFolders{end+1} = p; %#ok<AGROW>
        end
    end

    for d = 1:numel(seriesFolders)
        srcPath = seriesFolders{d};
        [~, folderName] = fileparts(srcPath);           % e.g. SMS4_BOLD_REST4_0005
        destPath = fullfile(nifti_sess_dir, folderName);
        if ~exist(destPath, 'dir'), mkdir(destPath); end

        system([dcm2niix, ' -f TEMPCONV_%s -i y -w 1 -o "', destPath, '" "', srcPath, '"']);

        generatedFiles = dir(fullfile(destPath, 'TEMPCONV_*'));
        for f = 1:length(generatedFiles)
            oldName = generatedFiles(f).name;
            newName = strrep(oldName, 'TEMPCONV', folderName);
            movefile(fullfile(destPath, oldName), fullfile(destPath, newName));
        end
    end
end

%% step 3: cleanup (Subfolder-Aware)
addpath(genpath('D:/software/jsonlab-master'));
imagedir = dir(fullfile(nifti_subj_dir, '**/*.json'));
imagedir(startsWith({imagedir.name}, '.')) = [];

unique_keys = cell(length(imagedir), 1);
for i = 1:length(imagedir)
    [~, fname, ~] = fileparts(imagedir(i).name);
    parts = split(fname, '_');
    % Key = folder location + everything but the series number
    unique_keys{i} = [imagedir(i).folder, '_', strjoin(parts(1:end-1), '_')];
end

[~, idx_unique] = unique(unique_keys, 'last');
dele_idx = setdiff(1:length(imagedir), idx_unique);

for i = 1:length(imagedir)
    [~, filename, ~] = fileparts(imagedir(i).name);
    json = loadjson(fullfile(imagedir(i).folder, imagedir(i).name));
    if contains(upper(json.ProtocolName), 'AAHEAD_SCOUT') || ismember(i, dele_idx)
        delete(fullfile(imagedir(i).folder, [filename, '*']));
    end
end

imagedir = dir(fullfile(nifti_subj_dir, '**/*.json'));
imagedir(startsWith({imagedir.name}, '.')) = [];

%% step 4: make bids dir
bidssubj = fullfile(BIDSFolder, ['sub-', subj]);
types = {'func', 'fmap', 'dwi', 'anat'};
for t = 1:length(types)
    if ~exist(fullfile(bidssubj, types{t}), 'dir'), mkdir(fullfile(bidssubj, types{t})); end
end

%% step 5: Copy to BIDS (session-aware IntendedFor; supports .nii and .nii.gz)

% -------- 5.0 Build sessName -> sesIndex map from MRIdata direct children --------
sess = dir(dicomFolder);
sess = sess([sess.isdir]);
sess(ismember({sess.name},{'.','..'})) = [];

sessRunMap = containers.Map('KeyType','char','ValueType','double');
for si = 1:numel(sess)
    sessRunMap(sess(si).name) = si;   % scan order index (used for grouping only)
end

% -------- 5.1 Precompute IntendedFor targets per session --------
sessionIntended = containers.Map('KeyType','char','ValueType','any');

for k = 1:length(imagedir)
    parentDir_k = imagedir(k).folder;

    try
        [sessName_k, seriesFolder_k] = getSessAndSeries(parentDir_k, nifti_subj_dir);
    catch
        continue
    end
    if ~isKey(sessRunMap, sessName_k), continue; end %#ok<NASGU>

    [~, fname_k, ~] = fileparts(imagedir(k).name);
    json_k = loadjson(fullfile(parentDir_k, imagedir(k).name));
    pn_k = lower(json_k.ProtocolName);

    series_upper_k = upper(seriesFolder_k);
    fname_upper_k  = upper(fname_k);

    if ~(contains(pn_k, 'bold') || contains(fname_upper_k, 'BOLD'))
        continue
    end

    dest_prefix_k = '';
    if contains(series_upper_k, 'REST')
        tok = regexp(series_upper_k, 'REST(\d+)', 'tokens', 'once');
        if isempty(tok), tok = {'1'}; end
        dest_prefix_k = sprintf('sub-%s_task-rest_run-%s', subj, tok{1});
    elseif contains(series_upper_k, 'SST')
        dest_prefix_k = sprintf('sub-%s_task-sst', subj);
    elseif contains(series_upper_k, 'NBACK')
        dest_prefix_k = sprintf('sub-%s_task-nback', subj);
    elseif contains(series_upper_k, 'SWITCH')
        dest_prefix_k = sprintf('sub-%s_task-switch', subj);
    end
    if isempty(dest_prefix_k), continue; end

    [~, ext_k] = pickNiftiFile(parentDir_k, fname_k);
    target = sprintf('func/%s_bold%s', dest_prefix_k, ext_k);

    if ~isKey(sessionIntended, sessName_k)
        sessionIntended(sessName_k) = {target};
    else
        sessionIntended(sessName_k) = unique([sessionIntended(sessName_k), {target}], 'stable');
    end
end

% -------- 5.2 Main loop: copy everything into BIDS --------
for i = 1:length(imagedir)
    parentDir = imagedir(i).folder;
    [~, filename, ~] = fileparts(imagedir(i).name);

    json = loadjson(fullfile(parentDir, [filename, '.json']));
    pn = lower(json.ProtocolName);
    fname_upper = upper(filename);

    try
        [sessName, seriesFolder] = getSessAndSeries(parentDir, nifti_subj_dir);
    catch
        sessName = ''; seriesFolder = '';
    end
    series_upper = upper(seriesFolder);

    if ~isempty(sessName) && isKey(sessRunMap, sessName)
        sesIdx = sessRunMap(sessName);
    else
        sesIdx = 1; % fallback
    end

    % choose .nii or .nii.gz for this file
    [srcImg, ext] = pickNiftiFile(parentDir, filename);

    % -------- Decide functional prefix (NO ses in func name; REST run from REST(\d+)) --------
    dest_prefix = '';
    if contains(series_upper, 'REST')
        tok = regexp(series_upper, 'REST(\d+)', 'tokens', 'once');
        if isempty(tok), tok = {'1'}; end
        dest_prefix = sprintf('sub-%s_task-rest_run-%s', subj, tok{1});
    elseif contains(series_upper, 'SST')
        dest_prefix = sprintf('sub-%s_task-sst', subj);
    elseif contains(series_upper, 'NBACK')
        dest_prefix = sprintf('sub-%s_task-nback', subj);
    elseif contains(series_upper, 'SWITCH')
        dest_prefix = sprintf('sub-%s_task-switch', subj);
    end

    % -------- 1) Functional --------
    if (contains(pn, 'bold') || contains(fname_upper, 'BOLD')) && ~isempty(dest_prefix)
        json.TaskName = regexp(dest_prefix, '(?<=task-)[a-z]+', 'match', 'once');
        savejson('', json, fullfile(parentDir, [filename, '.json']));

        copyfile(srcImg, fullfile(bidssubj, 'func', [dest_prefix, '_bold', ext]));
        copyfile(fullfile(parentDir, [filename, '.json']), fullfile(bidssubj, 'func', [dest_prefix, '_bold.json']));

    % -------- 2) Field Maps (Spin Echo) --------
    elseif contains(pn, 'se_2mm') || contains(fname_upper, 'SE_2MM')
        direc = 'PA';
        if contains(fname_upper, '_AP'), direc = 'AP'; end

        % IntendedFor within THIS session (include all rest/tasks in that session)
        if ~isempty(sessName) && isKey(sessionIntended, sessName)
            json.IntendedFor = sessionIntended(sessName);
        else
            json.IntendedFor = {};
        end
        savejson('', json, fullfile(parentDir, [filename, '.json']));

        % ONE output per session+direction; repeats overwrite
        fmap_name = sprintf('sub-%s_dir-%s_run-%02d_epi', subj, direc, sesIdx);

        copyfile(srcImg, fullfile(bidssubj, 'fmap', [fmap_name, ext]));
        copyfile(fullfile(parentDir, [filename, '.json']), fullfile(bidssubj, 'fmap', [fmap_name, '.json']));

    % -------- 3) Diffusion --------
    elseif contains(pn, 'diff') || contains(fname_upper, 'DIFF')

        if contains(pn, 'b0_ap') || contains(fname_upper, 'B0_AP')
            % IntendedFor points to the main dwi file (no ses in its name)
            json.IntendedFor = sprintf('dwi/sub-%s_dir-PA_dwi%s', subj, ext); % ext matches actual dwi file ext
            savejson('', json, fullfile(parentDir, [filename, '.json']));

            copyfile(srcImg, fullfile(bidssubj, 'fmap', ['sub-', subj, '_acq-dwi_dir-AP_epi', ext]));
            copyfile(fullfile(parentDir, [filename, '.json']), fullfile(bidssubj, 'fmap', ['sub-', subj, '_acq-dwi_dir-AP_epi.json']));

        elseif contains(pn, '_pa') || contains(fname_upper, '_PA')
            copyfile(srcImg, fullfile(bidssubj, 'dwi', ['sub-', subj, '_dir-PA_dwi', ext]));
            copyfile(fullfile(parentDir, [filename, '.json']), fullfile(bidssubj, 'dwi', ['sub-', subj, '_dir-PA_dwi.json']));
            copyfile(fullfile(parentDir, [filename, '.bvec']), fullfile(bidssubj, 'dwi', ['sub-', subj, '_dir-PA_dwi.bvec']));
            copyfile(fullfile(parentDir, [filename, '.bval']), fullfile(bidssubj, 'dwi', ['sub-', subj, '_dir-PA_dwi.bval']));
        end

    % -------- 4) Structural --------
    elseif contains(pn, 't1_mprage') || contains(fname_upper, 'T1_MPRAGE')
        copyfile(srcImg, fullfile(bidssubj, 'anat', ['sub-', subj, '_T1w', ext]));
        copyfile(fullfile(parentDir, [filename, '.json']), fullfile(bidssubj, 'anat', ['sub-', subj, '_T1w.json']));

    elseif contains(pn, 't2_spc') || contains(fname_upper, 'T2_SPC')
        copyfile(srcImg, fullfile(bidssubj, 'anat', ['sub-', subj, '_T2w', ext]));
        copyfile(fullfile(parentDir, [filename, '.json']), fullfile(bidssubj, 'anat', ['sub-', subj, '_T2w.json']));
    end
end

%% events.tsv
PSYCHdir=dir(strcat(PSYCHpath, '/*csv'));

for i =1:length(PSYCHdir)
    PSYCH=readtable(strcat(PSYCHdir(i).folder, '/',PSYCHdir(i).name));
    MRIstart_time=PSYCH.MRI_Signal_s_started(1)+PSYCH.MRI_Signal_s_rt(1);
    delete_idx=find(isnan(PSYCH.Trial_fix_started));
    PSYCH(delete_idx,:)=[];
    height_row=size(PSYCH,1);
    events=table('Size',[height_row 5],'VariableTypes',{'double','double','string', 'double', 'double'});
    events.Properties.VariableNames={'onset', 'duration', 'trial_type', 'response_time', 'value'};

    fname = PSYCHdir(i).name;
    parts = split(fname, '_');
    taskname = parts{5};

    for j=1:height_row
        events.onset(j)=PSYCH.Trial_fix_started(j)-MRIstart_time;
        events.duration(j)=PSYCH.key_resp_stopped(j)-PSYCH.Trial_fix_started(j);
        events.response_time(j)=PSYCH.key_resp_rt(j);
        events.value(j)=PSYCH.key_resp_corr(j);
    end

    if strcmp(taskname, 'SST')
        for j=1:height_row
            if strcmp(PSYCH.bad{j}, 'None'), events.trial_type(j)='go'; else, events.trial_type(j)='stop'; end
        end
    elseif strcmp(taskname, 'nback')
        for j=1:height_row
            if contains(PSYCH.Trial_loop_list{j}, '0back'), events.trial_type(j)='0back'; else, events.trial_type(j)='2back'; end
        end
    elseif strcmp(taskname, 'switch')
        for j=1:height_row
            if contains(PSYCH.Trial_loop_list{j}, 'nonswitch'), events.trial_type(j)='nonswitch'; else, events.trial_type(j)='switch'; end
        end
    end

    if strcmp(taskname, 'SST')
        writetable(events, [bidssubj, '/func/sub-', subj, '_task-sst_events.tsv'], 'FileType', 'text', 'Delimiter', '\t');
    else
        writetable(events, [bidssubj, '/func/sub-', subj, '_task-', taskname, '_events.tsv'], 'FileType', 'text', 'Delimiter', '\t');
    end
end
end

%% ===================== local helper functions =====================
function fmapInfo = getMultiSubfolderFmapInfo(dicomFolder, subj)
    fmapInfo = struct('seriesnum', {}, 'protocolkey', {}, 'acq', {}, 'IntendedFor', {});
    topdir = dir(dicomFolder);
    topdir = topdir([topdir.isdir]);
    topnames = {topdir.name};
    topdir(ismember(topnames,{'.','..'})) = [];
    for i = 1:length(topdir)
        thisPath = fullfile(topdir(i).folder, topdir(i).name);
        fmapInfo = scanOneBranch(thisPath, subj, fmapInfo);
    end
end

function fmapInfo = scanOneBranch(currPath, subj, fmapInfo)
    subdirs = dir(currPath);
    subdirs = subdirs([subdirs.isdir]);
    subnames = {subdirs.name};
    subdirs(ismember(subnames,{'.','..'})) = [];
    if isempty(subdirs), return; end
    dirNames = string({subdirs.name});
    upperNames = upper(dirNames);

    if any(contains(upperNames, 'SE_2MM'))
        hasRest = any(contains(upperNames, 'REST'));
        hasTask = any(contains(upperNames, 'SST')) || any(contains(upperNames, 'NBACK')) || any(contains(upperNames, 'SWITCH'));
        intended = strings(1,0);
        for j = 1:length(dirNames)
            nmUpper = upperNames(j);
            if contains(nmUpper, 'REST')
                rt = regexp(char(nmUpper), 'REST(\d+)', 'tokens', 'once');
                if ~isempty(rt), intended(end+1) = sprintf('func/sub-%s_task-rest_run-%s_bold.nii', subj, rt{1}); end
            elseif contains(nmUpper, 'SST'),    intended(end+1) = sprintf('func/sub-%s_task-sst_bold.nii', subj);
            elseif contains(nmUpper, 'NBACK'),  intended(end+1) = sprintf('func/sub-%s_task-nback_bold.nii', subj);
            elseif contains(nmUpper, 'SWITCH'), intended(end+1) = sprintf('func/sub-%s_task-switch_bold.nii', subj);
            end
        end
        intended = unique(intended, 'stable');
        for j = 1:length(subdirs)
            nmUpper = upperNames(j);
            if contains(nmUpper, 'SE_2MM')
                ser = regexp(char(subdirs(j).name), '_(\d+)$', 'tokens', 'once');
                if ~isempty(ser)
                    entry.seriesnum = str2double(ser{1});
                    entry.protocolkey = upper(regexprep(char(subdirs(j).name), '_\d+$', ''));
                    if hasTask, entry.acq = 'task'; else, entry.acq = 'rest'; end
                    entry.IntendedFor = intended;
                    fmapInfo(end+1) = entry;
                end
            end
        end
        return;
    end
    for j = 1:length(subdirs)
        nextPath = fullfile(subdirs(j).folder, subdirs(j).name);
        fmapInfo = scanOneBranch(nextPath, subj, fmapInfo);
    end
end

function [sessName, seriesName] = getSessAndSeries(parentDir, nifti_subj_dir)
    rel = erase(parentDir, [nifti_subj_dir filesep]);
    parts = strsplit(rel, filesep);

    sessName = parts{1};
    seriesName = parts{end};
end

function [srcImg, ext] = pickNiftiFile(parentDir, filename)
    pNii   = fullfile(parentDir, [filename, '.nii']);
    pNiiGz = fullfile(parentDir, [filename, '.nii.gz']);

    if exist(pNii, 'file')
        srcImg = pNii;
        ext = '.nii';
    elseif exist(pNiiGz, 'file')
        srcImg = pNiiGz;
        ext = '.nii.gz';
    else
        error('Cannot find NIfTI for %s in %s', filename, parentDir);
    end
end