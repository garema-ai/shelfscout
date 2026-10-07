# ShelfScout

**A small FMCG price-checking project for kirana and modern retail.** ShelfScout compares listed prices for candidate matches of the same product across store formats, shows where a gap needs investigation, and makes uncertain observations visible.

**Demo:** [Open the dashboard](https://garema-ai.github.io/shelfscout/) *(available after GitHub Pages is enabled)*

> **Portfolio disclosure:** This is an independent practice project. The included sunscreen products, stores, and prices are synthetic. The dashboard illustrates a method; its findings do not describe real shops or market prices.

## The question

When a product appears in a neighborhood kirana and a modern retail store, is the observed listed price different? A useful answer first checks pack size, promotional status, unclear prices, repeat observations, and whether the price sources are comparable.

## What I built

- A **Python analysis script** that reads the sample CSV, checks the observations, compares eligible prices, and writes a `report.json` file.
- A **static interactive dashboard** that displays precomputed results from the synthetic sample. It can be shared free through GitHub Pages. The webpage does not execute Python or automatically update when a new CSV is analyzed.
- A **review queue** for unclear or conflicting prices, so a person can check the original observation before treating a gap as a finding. Candidate product matches are labeled separately in the dashboard.

The matching rule is brand + variant + pack size **with unit**. This produces a *candidate match*, not proof of an identical SKU. A barcode check would strengthen it. For each format, the script uses the median of eligible store-level listed prices; the displayed difference is **modern minus kirana**. Promotional or unclear prices and conflicting observations are excluded from regular-price comparisons.

## Files

| File | Purpose |
| --- | --- |
| `index.html` | Self-contained dashboard with sample results |
| `price_agent.py` | Rules-based CSV analysis; Python standard library only |
| `sample_shelf_data.csv` | Fictional shelf observations for the demo |
| `README.md` | Project context, limits, and setup |

## Try the analysis

With Python 3.10 or newer, download these four files into **the same folder** and run:

```bash
python3 price_agent.py
```

The script writes `report.json` beside the files. You can also open `index.html` directly to explore the bundled demonstration. The dashboard is a snapshot of the sample analysis; running the script does not change its embedded data.

For a different CSV, use `python3 price_agent.py --input my_audit.csv --output my_report.json`. Keep real store observations and generated reports off a public repository unless you have permission to share them.

## Publish the dashboard with GitHub Pages

The intended repository is [`garema-ai/shelfscout`](https://github.com/garema-ai/shelfscout). Place the **four files above at the top level** of that repository, so `index.html` is visible immediately when you open the Code tab. On GitHub, choose **Add file → Upload files**, select the four individual files, and commit them to `main`. Do not upload the ZIP as a single file or put the four files inside an extra `ShelfScout` folder.

Then open **Settings → Pages → Build and deployment**. Choose **Deploy from a branch**, select **main** and **/(root)**, and save. The dashboard URL will be <https://garema-ai.github.io/shelfscout/> once GitHub finishes publishing. [GitHub's Pages instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site) show these settings.

If the repository still contains folders from an earlier version, check the Code tab and Pages setting against this four-file layout before sharing the link. This README describes the flat version.

## What the results mean

The sample shows how a researcher could prioritize a closer look at a price gap and document data-quality issues. It cannot establish a market trend, a customer's checkout price, or why prices differ. This is a small fictional dataset, and text-based product matching needs manual confirmation. Real fieldwork would also record barcodes, visit dates, price source (such as shelf tag versus printed MRP), and promotional conditions.

**Portfolio summary:** *Built an independent, rules-based FMCG shelf price audit that checks candidate product matches across retail formats, flags uncertain data, and presents reviewable comparisons in a shareable dashboard using synthetic observations.*
