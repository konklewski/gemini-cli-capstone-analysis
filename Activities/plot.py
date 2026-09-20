import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import colorsys
import matplotlib.colors as mcolors

FONT_PATH = "assets/GoogleSansFlexVariable.ttf"
CSV_PATH = "github_activity_events.csv"

font_path = FONT_PATH
fm.fontManager.addfont(font_path)
custom_font = fm.FontProperties(fname=font_path).get_name()

plt.style.use('dark_background')
plt.rcParams['font.family'] = custom_font

def brighten_color(hex_color):
    """Brightens a hex color by scaling its value/lightness in HSV space."""
    rgb = mcolors.to_rgb(hex_color)
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    # Decrease saturation slightly and increase value/brightness
    new_s = max(0.0, s * 0.2)
    new_v = min(1.0, v + (1.0 - v) * 0.9)
    return colorsys.hsv_to_rgb(h, new_s, new_v)

# Load CSV
df = pd.read_csv(CSV_PATH)
df['Date'] = pd.to_datetime(df['Date'])

# Group by Activity type and week start
activity = (
    df.groupby(['Type', pd.Grouper(key='Date', freq='W-MON')])
    .size()
    .unstack(level=0, fill_value=0)
)

# Setup Plotting Layout
fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

color_bg = '#1B1A1D'
color_fg = "#e7e7ff"

colors = {
    'Commit': "#6fd341",
    'Issue': "#ee733a",
    'PullRequest': "#4cd4e6"
}

# Mapping main activity types to their corresponding 'closed' event type
activity_pairs = [
    ('Commit', None),
    ('Issue', 'IssueClosed'),
    ('PullRequest', 'PullRequestClosed')
]

for ax, (act_type, closed_type) in zip(axes, activity_pairs):
    base_color = colors.get(act_type, '#58a6ff')

    # Plot Created
    if act_type in activity.columns:
        counts = activity[act_type]
        total_count = counts.sum()

        ax.plot(
            counts.index,
            counts,
            color=base_color,
            linewidth=1.5,
            marker='o',
            markersize=3,
            alpha=0.85,
            label='Opened / Created'
        )
        ax.fill_between(counts.index, counts, color=base_color, alpha=0.12)
        if (closed_type):
            title_str = f'Weekly {act_type} Activity (Opened: {total_count}'
        else:
            title_str = f'Weekly {act_type} Activity (Total: {total_count}'
    else:
        title_str = f'Weekly {act_type} Activity (Opened: 0'

    # Plot Closed
    if closed_type and closed_type in activity.columns:
        closed_counts = activity[closed_type]
        total_closed = closed_counts.sum()
        brighter_color = brighten_color(base_color)

        ax.plot(
            closed_counts.index,
            closed_counts,
            color=brighter_color,
            linewidth=1.75,
            linestyle='--',
            marker='x',
            markersize=4,
            alpha=0.95,
            label='Closed'
        )
        title_str += f' | Closed: {total_closed})'
    else:
        title_str += ')'

    ax.set_facecolor(color_bg)
    ax.set_title(title_str, fontsize=15, loc='left', color=color_fg)
    ax.set_ylabel('Count', fontsize=12, color=color_fg)
    ax.legend(loc='upper right', frameon=False, fontsize=10)
    ax.grid(True, axis='y', linestyle='--', alpha=0.2, color=color_fg)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#8b949e')
    ax.spines['bottom'].set_color('#8b949e')

# Format X-Axis
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=1))
plt.xticks(rotation=45, color=color_fg)
plt.xlabel('Date', fontsize=11, color=color_fg)

fig.patch.set_facecolor(color_bg)
plt.suptitle('google-gemini/gemini-cli Activity Overview', fontsize=20, y=0.98, color=color_fg)
plt.tight_layout()

plt.show()
