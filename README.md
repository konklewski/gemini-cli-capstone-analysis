## Analysis scripts for gemini-cli

_for Capstone Software Development course_

### Interm assignment

See the `Interim/` folder.

- The `Activities` subfolder holds code used for the Activities part of the report
- The `Contributor_Collaboration` subfolder holds code used for the Contributor and Collaboration parts of the report

Each subfolder has its own readme with usage instructions.

### Final assignment

See the `Final/` folder.

- The `Health` folder contains project health analysis scripts, manual account evidence, result tables and figures. See its readme for usage instructions.
- The `Quality` folder contains configurations and artifacts for the measurements in the Quality section of the report
  - `coupling-report.json` and `coupling-counts.txt`: File dependency analysis results. The former is a file dependency list, the latter is dependency counts along with file names
  - `packages.und`: SciTools Understand configuration used to analyze `gemini-cli`'s `packages` folder
  - `packages.csv`: A SciTools Understand export of code line count and cyclomatic complexity metrics to .csv format for inspection in Excel

