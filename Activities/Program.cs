using Octokit;
using DotNetEnv;

public class CommitRecord {
    public string Sha { get; set; } = "";
    public DateTimeOffset Date { get; set; }
    public string Message { get; set; } = "";
}

public class IssueRecord {
    public int Number { get; set; }
    public string Title { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; }
    public DateTimeOffset? ClosedAt { get; set; }
    public string State { get; set; } = "";
    public string HtmlUrl { get; set; } = "";
}

class Program {
    static async Task Stuff() {
        Console.WriteLine("Fetching data from GitHub API...");

        Env.Load();
        string? githubToken = Environment.GetEnvironmentVariable("GITHUB_TOKEN");
        if (string.IsNullOrEmpty(githubToken))
            throw new InvalidOperationException("GITHUB_TOKEN is missing from the .env file.");

        var client = new GitHubClient(new ProductHeaderValue("CapstoneSoftwareDevCourseExercise")) {
            Credentials = new Credentials(githubToken)
        };

        string owner = "google-gemini";
        string repo = "gemini-cli";

        DateTimeOffset startDate = new DateTimeOffset(2025, 9, 17, 0, 0, 0, TimeSpan.Zero);
        DateTimeOffset endDate = new DateTimeOffset(2026, 9, 17, 23, 59, 59, TimeSpan.Zero);

        // Fetch Commits
        Console.WriteLine("Fetching commits...");
        var commitRequest = new CommitRequest {
            Since = startDate,
            Until = endDate
        };
        var rawCommits = await client.Repository.Commit.GetAll(owner, repo, commitRequest);

        // Fetch Issues & PRs
        Console.WriteLine("Fetching issues and PRs...");
        var issueRequest = new RepositoryIssueRequest { State = ItemStateFilter.All };
        var rawIssuesAndPrs = await client.Issue.GetAllForRepository(owner, repo, issueRequest);

        var commits = rawCommits
            .Where(c => c.Commit.Author.Date >= startDate && c.Commit.Author.Date <= endDate)
            .Select(c => new CommitRecord {
                Sha = c.Sha,
                Date = c.Commit.Author.Date,
                Message = c.Commit.Message.Split('\n')[0]
            }).ToList();

        var issues = rawIssuesAndPrs
            .Where(i => i.PullRequest == null && i.CreatedAt >= startDate && i.CreatedAt <= endDate)
            .Select(i => new IssueRecord {
                Number = i.Number,
                Title = i.Title,
                CreatedAt = i.CreatedAt,
                ClosedAt = i.ClosedAt,
                State = i.State.Value.ToString(),
                HtmlUrl = i.HtmlUrl
            }).ToList();

        var pullRequests = rawIssuesAndPrs
            .Where(i => i.PullRequest != null && i.CreatedAt >= startDate && i.CreatedAt <= endDate)
            .Select(i => new IssueRecord {
                Number = i.Number,
                Title = i.Title,
                CreatedAt = i.CreatedAt,
                ClosedAt = i.ClosedAt,
                State = i.State.Value.ToString(),
                HtmlUrl = i.HtmlUrl
            }).ToList();

        // Calculate Closed Metrics
        int closedIssuesCount = issues.Count(i => i.ClosedAt != null);
        int closedPrsCount = pullRequests.Count(p => p.ClosedAt != null);

        // Results
        Console.WriteLine("\n=== SUMMARY ===");
        Console.WriteLine($"Total Commits: {commits.Count}");
        Console.WriteLine($"Total Issues:  {issues.Count}");
        Console.WriteLine($"  └─ Issues Closed:        {closedIssuesCount}");
        Console.WriteLine($"Total PRs:     {pullRequests.Count}");
        Console.WriteLine($"  └─ PRs Closed:           {closedPrsCount}");

        // Export a CSV for easy plotting later
        // Export CSV with Created and Closed dates
        var csvLines = new List<string> { "Type,Id,Date,Title" };

        // Commits
        csvLines.AddRange(commits.Select(c => $"Commit,{c.Sha},{c.Date:yyyy-MM-dd},\"{c.Message.Replace("\"", "\"\"")}\""));

        // Issues Created & Closed
        csvLines.AddRange(issues.Select(i => $"Issue,{i.Number},{i.CreatedAt:yyyy-MM-dd},\"{i.Title.Replace("\"", "\"\"")}\""));
        csvLines.AddRange(issues.Where(i => i.ClosedAt.HasValue).Select(i => $"IssueClosed,{i.Number},{i.ClosedAt!.Value:yyyy-MM-dd},\"{i.Title.Replace("\"", "\"\"")}\""));

        // PRs Created & Closed
        csvLines.AddRange(pullRequests.Select(p => $"PullRequest,{p.Number},{p.CreatedAt:yyyy-MM-dd},\"{p.Title.Replace("\"", "\"\"")}\""));
        csvLines.AddRange(pullRequests.Where(p => p.ClosedAt.HasValue).Select(p => $"PullRequestClosed,{p.Number},{p.ClosedAt!.Value:yyyy-MM-dd},\"{p.Title.Replace("\"", "\"\"")}\""));

        await File.WriteAllLinesAsync("github_activity_events.csv", csvLines);
        Console.WriteLine("Exported events to github_activity_events.csv");
    }

    static async Task Main(string[] args) {
        await Stuff();
    }
}
