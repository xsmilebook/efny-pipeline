function task = classify_psychopy_task(fileName)
%CLASSIFY_PSYCHOPY_TASK Identify one supported task from filename tokens.
%
% Task names must be delimited by underscores so participant identifiers or
% other filename text cannot create a partial task-name match.

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
