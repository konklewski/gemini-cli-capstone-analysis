# gemini-cli project quality analysis

## File dependencies

- `coupling-report.json`
- `coupling-counts.txt`: File dependency analysis results. The former is a file dependency list, the latter is dependency counts along with file names

## Line count & Cyclomatic complexity

- `packages.und`: SciTools Understand configuration used to analyze `gemini-cli`'s `packages` folder
- `packages.csv`: A SciTools Understand export of code line count and cyclomatic complexity metrics to .csv format for inspection in Excel

## Line code coverage

Generated reports are in the `coverage_reports` folder for the measured packages, namely `a2a-server`, `cli`, and `core`. To open the report of a package, go to its folder and open the `index.html` file in a browser.

## Improvement proposals

See the `improvements` folder, which contains its own `README.md`

