# Snowflake Value Realization Hub

A searchable catalog of 46 Snowflake-branded value realization slides — one per solution repo — built for Snowflake field teams.

**Live site:** https://sfc-gh-michael-lemke.github.io/snowflake-value-hub/

## Pages

| Page | Description |
|------|-------------|
| [Home](index.html) | Introduction, personas, how it works, and how to contribute |
| [Catalog](catalog.html) | Browse and filter all 46 solution slides |

## Feedback

[Leave feedback →](https://docs.google.com/forms/d/e/1FAIpQLScflxOQu-Scwyf99eQr3ZutKErJje2SrHPI-8vvQqQVGszJWQ/viewform)

---

## Contributing — Add Your Slide

The catalog grows through contributions. If you have a Snowflake solution documented in a GitHub repo, use the **value-realization-slide** CoCo skill to generate a branded slide.

### Step 1: Install the skill in CoCo

```
Install plugin from GitHub: https://github.com/sfc-gh-michael-lemke/value-realization-slide
```

### Step 2: Run it against your repo

```
/value-realization-slide https://github.com/your-org/your-repo
```

The skill fetches your README, analyzes the content, and produces a Snowflake 2026-branded HTML slide saved to `~/Downloads/your-repo-value-realization.html`.

### Step 3: Commit the slide to your repo

```bash
cp ~/Downloads/your-repo-value-realization.html value-realization.html
git add value-realization.html && git commit -m "docs: add value realization slide" && git push
```

### Step 4: Submit to the Hub

Open the [feedback form](https://docs.google.com/forms/d/e/1FAIpQLScflxOQu-Scwyf99eQr3ZutKErJje2SrHPI-8vvQqQVGszJWQ/viewform) with your repo URL to request inclusion in the catalog.

---

## Maintainer

Michael Lemke — RevOps, Snowflake
