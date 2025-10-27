# Quick Start Guide

Get up and running with Scout Mailchimp Sync in 5 minutes.

## Step 1: Install Dependencies

```bash
# Install Python packages
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium
```

## Step 2: Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your credentials
nano .env  # or use your preferred editor
```

Required values in `.env`:
```env
SCOUTBOOK_USERNAME=your_email@example.com
SCOUTBOOK_PASSWORD=your_password
MAILCHIMP_API_KEY=your_api_key
MAILCHIMP_SERVER_PREFIX=us19  # check your API key
MAILCHIMP_AUDIENCE_ID=your_audience_id
```

## Step 3: Run a Test (Dry Run)

```bash
# This will show you what would be updated without making changes
python scout_mailchimp_sync.py --dry-run
```

Review the output to ensure everything looks correct.

## Step 4: Sync for Real

```bash
# This will actually update your Mailchimp audience
python scout_mailchimp_sync.py --live
```

## Need Help?

- See [README.md](README.md) for detailed documentation
- Check the troubleshooting section for common issues
- Review the output messages - they provide helpful error details

## Tips

- Always run `--dry-run` first to preview changes
- Check your Mailchimp audience has the required merge fields
- Run with `SCOUTBOOK_HEADLESS=false` in `.env` to see the browser if debugging
