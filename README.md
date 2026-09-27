# Review Ingestion Workflow (Sciencia AI)

Collect review samples, save them in one database, and search the saved results.

**[Open the website](https://product-review-data.review-data-lab.workers.dev/)** — no account, installation or database download needed.

## Two versions

| Folder | What it contains |
| --- | --- |
| [Version 1](Version%201/) | The earlier Amazon experiment: collector, website and sample results. Kept for reference; work is paused because access was unreliable. |
| [Version 2](Version%202/) | The current Google Play workflow: collection, shared storage, search, website and tests. **Start here.** |

## Try it

1. Search **Google Maps** or **Spotify** to see reviews already saved in the database.
2. To collect another app, open **Add a review sample** and paste its Google Play link or app ID, for example `org.telegram.messenger`. Add its name and click **Collect latest sample**.
3. The returned reviews are saved online. Search them, filter by stars or helpful votes, or download JSON.

This collects reviews **of Android apps**, not physical products or places in Google Maps. New apps need their Google Play link or ID; searching a name only searches saved data.

The public preview requests up to 25 reviews per page, with up to three pages per run. It does not guarantee all reviews or the latest reviews. Scheduled updates are not enabled yet. See [Version 2](Version%202/) for the current limits and test results.
