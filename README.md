# Scout Mailchimp Sync

A Python script that automates syncing Scout roster data from Scoutbook to Mailchimp. This tool logs into Scoutbook, downloads the scout roster, transforms the data, and updates your Mailchimp audience with scout information.

## Features

- Automated login and data retrieval from Scoutbook
- Transforms scout data to group multiple scouts under parent email addresses
- Syncs scout information to Mailchimp (names, dens, expiration dates, addresses)
- Dry-run mode to preview changes before applying them
- All credentials stored securely in environment variables

## Prerequisites

- Python 3.7 or higher
- A Scoutbook account with access to scout rosters
- A Mailchimp account with an existing audience
- Mailchimp API key

## Installation

1. **Clone or download this repository**

2. **Install Python dependencies:**

```bash
pip install -r requirements.txt
```

3. **Install Playwright browsers:**

```bash
playwright install chromium
```

4. **Create your environment file:**

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Then edit `.env` with your actual credentials:

```env
# Scoutbook Credentials
SCOUTBOOK_USERNAME=your_email@example.com
SCOUTBOOK_PASSWORD=your_password

# Mailchimp Configuration
MAILCHIMP_API_KEY=your_api_key_here
MAILCHIMP_SERVER_PREFIX=us19
MAILCHIMP_AUDIENCE_ID=your_audience_id
```

### Getting Mailchimp Credentials

- **API Key**: In Mailchimp, go to Account > Extras > API keys
- **Server Prefix**: Look at your API key - it ends with something like `-us19`. Use that part (e.g., `us19`)
- **Audience ID**: Go to Audience > Settings > Audience name and defaults

## Usage

### Basic Usage

**Dry run (preview changes without applying):**
```bash
python scout_mailchimp_sync.py --dry-run
```

**Live sync (actually update Mailchimp):**
```bash
python scout_mailchimp_sync.py --live
```

**Default behavior (dry run):**
```bash
python scout_mailchimp_sync.py
```

### What the Script Does

1. **Fetches Data**: Logs into Scoutbook and downloads the scout roster
2. **Transforms Data**: Groups scouts by parent email address (supports up to 3 scouts per family)
3. **Syncs to Mailchimp**: Updates the following fields for each parent email:
   - Scout 1, Scout 2, Scout 3 (scout names)
   - Scout 1 Den, Scout 2 Den, Scout 3 Den
   - Scout 1 Expiratioin, Scout 2 Expiration, Scout 3 Expiration (BSA membership expiration)
   - ADDRESS (family address)

### Mailchimp Field Mapping

The script maps Scoutbook data to the following Mailchimp merge fields:

| Scoutbook Field | Mailchimp Field | Notes |
|-----------------|-----------------|-------|
| Scout Full Name | Scout 1, Scout 2, Scout 3 | Up to 3 scouts per email |
| Den/Grade | Scout 1 Den, Scout 2 Den, Scout 3 Den | Den or grade level |
| BSA Expiration | Scout 1 Expiratioin*, Scout 2 Expiration, Scout 3 Expiration | *Note the typo in Scout 1 field |
| Street, City, State, Zip | ADDRESS | Combined into single field |

## Environment Variables

All configuration is done through environment variables in the `.env` file:

| Variable | Required | Description |
|----------|----------|-------------|
| `SCOUTBOOK_USERNAME` | Yes | Your Scoutbook/MyScouting username (email) |
| `SCOUTBOOK_PASSWORD` | Yes | Your Scoutbook/MyScouting password |
| `SCOUTBOOK_HEADLESS` | No | Run browser in headless mode (true/false, default: true) |
| `MAILCHIMP_API_KEY` | Yes | Your Mailchimp API key |
| `MAILCHIMP_SERVER_PREFIX` | Yes | Your Mailchimp server prefix (e.g., us19) |
| `MAILCHIMP_AUDIENCE_ID` | Yes | Your Mailchimp audience ID |

## Security Notes

- The `.env` file contains sensitive credentials and is excluded from git via `.gitignore`
- Never commit your `.env` file to version control
- Keep your API keys and passwords secure
- The `.env.example` file is safe to commit as it contains no real credentials

## Troubleshooting

### Missing environment variables
If you see an error about missing environment variables, ensure your `.env` file exists and contains all required variables.

### Scoutbook login fails
- Verify your username and password are correct
- Try running with `SCOUTBOOK_HEADLESS=false` to see the browser window
- Check if Scoutbook has changed their login page structure

### Mailchimp sync errors
- Verify your API key, server prefix, and audience ID are correct
- Check that the merge fields exist in your Mailchimp audience
- Review any specific error messages in the output

### Address validation errors
If you see errors about incomplete addresses, you can either:
- Complete the address in Mailchimp manually, or
- Make the ADDRESS field optional in Mailchimp settings

## Development

This script was created by extracting and simplifying functionality from an existing scout-mailchimp project, removing Google Sheets dependencies and making all configuration environment-based.

## License

This project is provided as-is for use by Scout organizations.

## Support

For issues or questions, please refer to the script output which provides detailed error messages and troubleshooting tips.
