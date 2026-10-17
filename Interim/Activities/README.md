## gemini-cli activity analysis

### Instructions

```powershell
# First run the data fetcher
dotnet build -c release
dotnet "bin/Release/net10.0/CapSwDevProj.dll"

# Now there should be a file called github_activity_events.csv
# Use the python script to plot it:
python plot.py
```

