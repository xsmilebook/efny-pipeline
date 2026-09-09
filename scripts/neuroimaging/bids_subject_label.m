function label = bids_subject_label(sourceFolderName)
%BIDS_SUBJECT_LABEL Derive an alphanumeric BIDS participant label.

sourceFolderName = char(string(sourceFolderName));

token = regexp(sourceFolderName, ...
    '^([A-Za-z]+)[_-]\d{8}[_-](\d+)(?:[_-].*)?$', 'tokens', 'once');
if isempty(token)
    token = regexp(sourceFolderName, ...
        '^([A-Za-z]+)[_-](\d+)$', 'tokens', 'once');
end

if isempty(token)
    error('Cannot derive a participant label from source folder: %s', ...
        sourceFolderName);
end

label = [upper(token{1}), token{2}];
assert(~isempty(regexp(label, '^[A-Za-z0-9]+$', 'once')), ...
    'Invalid BIDS participant label derived from %s: %s', ...
    sourceFolderName, label);
end
