#!/usr/bin/env python3
"""
Scout Mailchimp Sync - Scoutbook to Mailchimp Integration

This script provides a data pipeline that:
1. Fetches scout roster data from Scoutbook
2. Transforms and groups scouts by parent email
3. Syncs to Mailchimp with correct field mappings

Usage:
    python scout_mailchimp_sync.py                 # Interactive mode
    python scout_mailchimp_sync.py --dry-run       # Dry run mode (default)
    python scout_mailchimp_sync.py --live          # Live sync to Mailchimp
    python scout_mailchimp_sync.py --help          # Show help
"""

import asyncio
import argparse
import sys
import os
import pandas as pd
import mailchimp_marketing as MailchimpMarketing
from dotenv import load_dotenv
import hashlib
import time
from playwright.async_api import async_playwright
import traceback
import json


# Load environment variables
load_dotenv()


class ScoutbookScraper:
    """Scraper for Scoutbook data using Playwright"""

    def __init__(self, download_dir="./scout_reports"):
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)

    async def fetch_scout_data_as_dataframe(self, username, password, headless=True):
        """
        Fetch scout roster data from Scoutbook and return as DataFrame

        Args:
            username: Scoutbook username
            password: Scoutbook password
            headless: Whether to run browser in headless mode

        Returns:
            pandas.DataFrame: Scout roster data
        """
        async with async_playwright() as p:
            try:
                print(f"Launching browser (headless={headless})...")
                browser = await p.chromium.launch(headless=headless)
                context = await browser.new_context(accept_downloads=True)
                page = await context.new_page()

                # Navigate to Scoutbook login
                print("Navigating to Scoutbook login...")
                await page.goto("https://scoutbook.scouting.org/mobile/login")

                # Wait for login page to load
                await page.wait_for_selector('input[name="username"]', timeout=10000)

                # Enter credentials
                print("Entering credentials...")
                await page.fill('input[name="username"]', username)
                await page.fill('input[name="password"]', password)

                # Click login button
                print("Logging in...")
                await page.click('button[type="submit"]')

                # Wait for navigation after login
                await page.wait_for_load_state("networkidle", timeout=30000)

                # Navigate to roster report
                print("Navigating to roster report...")
                await page.goto("https://scoutbook.scouting.org/mobile/dashboard/reports/roster")

                # Wait for report page to load
                await page.wait_for_load_state("networkidle", timeout=30000)

                # Click download button
                print("Downloading roster report...")
                async with page.expect_download() as download_info:
                    await page.click('button:has-text("Download")')
                    download = await download_info.value

                    # Save download
                    file_path = os.path.join(self.download_dir, "roster.csv")
                    await download.save_as(file_path)
                    print(f"Downloaded roster to {file_path}")

                # Close browser
                await browser.close()

                # Load CSV and return as DataFrame
                print("Loading roster data...")
                df = pd.read_csv(file_path, skiprows=10)  # Skip Scoutbook metadata
                print(f"Loaded {len(df)} scout records")

                return df

            except Exception as e:
                print(f"Error fetching Scoutbook data: {str(e)}")
                print(traceback.format_exc())
                return pd.DataFrame()


def setup_mailchimp_client():
    """Initialize Mailchimp API client with credentials from .env file"""
    api_key = os.getenv("MAILCHIMP_API_KEY")
    server = os.getenv("MAILCHIMP_SERVER_PREFIX")
    audience_id = os.getenv("MAILCHIMP_AUDIENCE_ID")

    if not all([api_key, server, audience_id]):
        raise ValueError(
            "Missing Mailchimp configuration. Please check your .env file."
        )

    client = MailchimpMarketing.Client({"api_key": api_key, "server": server})

    return client, audience_id


def get_subscriber_hash(email):
    """Generate MD5 hash for email address (required by Mailchimp API)"""
    return hashlib.md5(email.lower().encode()).hexdigest()


def transform_scout_data(scoutbook_df):
    """
    Transform scout DataFrame to group multiple scouts under one email address.
    Each scout gets their own column (Scout 1, Scout 2, etc.) along with
    their corresponding dues status column.

    Args:
        scoutbook_df: pandas.DataFrame with Scoutbook data

    Returns:
        pandas.DataFrame: Transformed data grouped by email
    """
    try:
        print("Processing Scoutbook data...")

        # Clean column names (strip whitespace)
        scoutbook_df.columns = scoutbook_df.columns.str.strip()

        # Map actual Scoutbook columns to expected names
        column_mapping = {
            "..memberid": "__memberid",
            "firstname": "First Name",
            "lastname": "Last Name",
            "gradename": "Den",
            "pgprimaryemail": "pgprimaryemail",
            "expirydtstr": "expirydtstr",
            "streetaddress": "streetaddress",
            "city": "city",
            "statecode": "statecode",
            "zip9": "zip9",
        }

        # Check if all required source columns exist
        required_source_cols = list(column_mapping.keys())
        missing_required = [
            col for col in required_source_cols if col not in scoutbook_df.columns
        ]

        if missing_required:
            print(f"Error: Missing required Scoutbook columns: {missing_required}")
            print(f"Available Scoutbook columns: {list(scoutbook_df.columns)}")
            return pd.DataFrame()

        # Rename columns to match expected format
        scoutbook_df = scoutbook_df.rename(columns=column_mapping)

        # Create a "Name" column by combining firstname and lastname
        if "Name" not in scoutbook_df.columns:
            name_parts = []

            if "prefix" in scoutbook_df.columns:
                name_parts.append(scoutbook_df["prefix"].fillna(""))

            name_parts.append(scoutbook_df["First Name"].fillna(""))

            if "middlename" in scoutbook_df.columns:
                name_parts.append(scoutbook_df["middlename"].fillna(""))

            name_parts.append(scoutbook_df["Last Name"].fillna(""))

            scoutbook_df["Name"] = ""
            for part in name_parts:
                scoutbook_df["Name"] = (
                    scoutbook_df["Name"] + " " + part.astype(str)
                ).str.strip()

            scoutbook_df["Name"] = (
                scoutbook_df["Name"].str.replace(r"\s+", " ", regex=True).str.strip()
            )

        # Create full name column for scouts
        scoutbook_df["Full Name"] = (
            scoutbook_df["First Name"].fillna("") + " " +
            scoutbook_df["Last Name"].fillna("")
        )
        scoutbook_df["Full Name"] = scoutbook_df["Full Name"].str.strip()

        # Group by email and aggregate scout information
        result_data = []

        for email, group in scoutbook_df.groupby("pgprimaryemail"):
            if pd.isna(email) or email == "":
                continue

            # Start with email
            row_data = {"pgprimaryemail": email}

            # Get unique Den and Name info
            if "Den" in scoutbook_df.columns:
                row_data["Den"] = (
                    group["Den"].iloc[0] if not group["Den"].isna().all() else ""
                )
            if "Name" in scoutbook_df.columns:
                row_data["Name"] = (
                    group["Name"].iloc[0] if not group["Name"].isna().all() else ""
                )

            # Add address fields
            for addr_field in ["streetaddress", "city", "statecode", "zip9"]:
                if addr_field in scoutbook_df.columns:
                    row_data[addr_field] = (
                        group[addr_field].iloc[0]
                        if not group[addr_field].isna().all()
                        else ""
                    )

            # Add scouts and their information
            scout_num = 1
            for idx, scout in group.iterrows():
                scout_col = f"Scout {scout_num}"
                den_col = f"Scout {scout_num} Den"
                exp_col = f"Scout {scout_num} Expiry"

                # Add scout name
                row_data[scout_col] = scout["Full Name"] if scout["Full Name"] else ""

                # Add den information
                den_info = scout.get("Den", "")
                row_data[den_col] = den_info if not pd.isna(den_info) else ""

                # Add expiration information
                exp_info = scout.get("expirydtstr", "")
                row_data[exp_col] = exp_info if not pd.isna(exp_info) else ""

                scout_num += 1

            result_data.append(row_data)

        # Create result DataFrame
        result_df = pd.DataFrame(result_data)

        # Reorder columns
        base_cols = ["pgprimaryemail"]
        if "Den" in result_df.columns:
            base_cols.append("Den")
        if "Name" in result_df.columns:
            base_cols.append("Name")

        # Get scout columns and sort them
        scout_cols = [col for col in result_df.columns if col.startswith("Scout")]
        scout_cols.sort(
            key=lambda x: (
                int(x.split()[1]) if "Scout" in x and x.split()[1].isdigit() else 0
            )
        )

        # Final column order
        final_cols = base_cols + scout_cols
        result_df = result_df[final_cols]

        print("Transformation complete!")
        print(f"Processed {len(scoutbook_df)} original rows into {len(result_df)} email groups")
        print(f"Columns in output: {list(result_df.columns)}")

        return result_df

    except Exception as e:
        print(f"Error processing data: {str(e)}")
        print(traceback.format_exc())
        return pd.DataFrame()


def sync_to_mailchimp(transformed_df, dry_run=True):
    """
    Sync transformed DataFrame to Mailchimp audience

    Args:
        transformed_df: pandas.DataFrame with transformed scout data
        dry_run: If True, only show what would be done without making changes

    Returns:
        tuple: (success_count, error_count)
    """
    try:
        # Set up Mailchimp client
        client, audience_id = setup_mailchimp_client()

        print(
            f"{'DRY RUN: ' if dry_run else ''}Syncing {len(transformed_df)} records to Mailchimp audience..."
        )

        success_count = 0
        error_count = 0

        for idx, row in transformed_df.iterrows():
            email = row.get("pgprimaryemail", row.get("Email", ""))

            if pd.isna(email) or email == "":
                row_num = idx + 1 if isinstance(idx, int) else "unknown"
                print(f"Skipping row {row_num}: No email address")
                continue

            try:
                # Prepare merge fields - only scout-specific fields
                merge_fields = {}

                # Define allowed fields that can be updated
                allowed_fields = {
                    "Scout 1",
                    "Scout 2",
                    "Scout 3",
                    "Scout 1 Den",
                    "Scout 2 Den",
                    "Scout 3 Den",
                    "Scout 1 Expiratioin",  # Note: typo exists in Mailchimp
                    "Scout 2 Expiration",
                    "Scout 3 Expiration",
                    "ADDRESS",
                }

                # Map scout information to Mailchimp fields
                for scout_num in range(1, 4):  # Support up to 3 scouts
                    scout_col = f"Scout {scout_num}"
                    den_col = f"Scout {scout_num} Den"
                    exp_col = f"Scout {scout_num} Expiry"

                    # Map to actual Mailchimp field names
                    mailchimp_scout_field = f"Scout {scout_num}"
                    mailchimp_den_field = f"Scout {scout_num} Den"

                    # Handle expiration field name inconsistency
                    if scout_num == 1:
                        mailchimp_exp_field = f"Scout {scout_num} Expiratioin"
                    else:
                        mailchimp_exp_field = f"Scout {scout_num} Expiration"

                    # Add scout name
                    if (
                        mailchimp_scout_field in allowed_fields
                        and scout_col in row.index
                        and not pd.isna(row[scout_col])
                        and row[scout_col] != ""
                    ):
                        merge_fields[mailchimp_scout_field] = str(row[scout_col])

                    # Add den information
                    if (
                        mailchimp_den_field in allowed_fields
                        and den_col in row.index
                        and not pd.isna(row[den_col])
                        and row[den_col] != ""
                    ):
                        merge_fields[mailchimp_den_field] = str(row[den_col])

                    # Add expiration date
                    if (
                        mailchimp_exp_field in allowed_fields
                        and exp_col in row.index
                        and not pd.isna(row[exp_col])
                        and row[exp_col] != ""
                    ):
                        merge_fields[mailchimp_exp_field] = str(row[exp_col])

                # Add ADDRESS field if available
                if "ADDRESS" in allowed_fields:
                    address_parts = []

                    if (
                        "streetaddress" in row.index
                        and not pd.isna(row["streetaddress"])
                        and row["streetaddress"] != ""
                    ):
                        address_parts.append(str(row["streetaddress"]).strip())

                    if (
                        "city" in row.index
                        and not pd.isna(row["city"])
                        and row["city"] != ""
                    ):
                        city = str(row["city"]).strip()
                        if city:
                            address_parts.append(city)

                    if (
                        "statecode" in row.index
                        and not pd.isna(row["statecode"])
                        and row["statecode"] != ""
                    ):
                        state = str(row["statecode"]).strip()
                        if state:
                            address_parts.append(state)

                    if (
                        "zip9" in row.index
                        and not pd.isna(row["zip9"])
                        and row["zip9"] != ""
                    ):
                        zip_code = str(row["zip9"]).strip()
                        if zip_code:
                            address_parts.append(zip_code)

                    # Only add ADDRESS if we have at least street address
                    if len(address_parts) >= 1 and address_parts[0]:
                        full_address = ", ".join(address_parts)
                        merge_fields["ADDRESS"] = full_address

                if dry_run:
                    print(f"  Would update: {email}")
                    print(f"    Merge fields: {merge_fields}")
                else:
                    subscriber_hash = get_subscriber_hash(email)

                    # Skip if no fields to update
                    if not merge_fields:
                        print(f"  SKIPPED: {email} - No merge fields to update")
                        continue

                    try:
                        # Check if member exists
                        try:
                            existing_member = client.lists.get_list_member(
                                audience_id, subscriber_hash
                            )
                            member_exists = True
                            print(f"  Found existing member: {email}")
                        except Exception:
                            member_exists = False
                            print(f"  New member: {email}")

                        if member_exists:
                            # Update existing member
                            update_data = {"merge_fields": merge_fields}
                            response = client.lists.update_list_member(
                                audience_id, subscriber_hash, update_data
                            )
                            print(f"  Updated: {email} (Status: {response['status']})")
                        else:
                            # Create new member
                            member_info = {
                                "email_address": email,
                                "status_if_new": "subscribed",
                                "merge_fields": merge_fields,
                            }
                            response = client.lists.set_list_member(
                                audience_id, subscriber_hash, member_info
                            )
                            print(f"  Created: {email} (Status: {response['status']})")

                    except Exception as update_error:
                        error_text = str(update_error)
                        if hasattr(update_error, "text"):
                            error_text = getattr(update_error, "text", str(update_error))

                        print(f"  Error updating {email}: {error_text}")
                        raise

                success_count += 1

                # Rate limiting
                if not dry_run:
                    time.sleep(0.1)

            except Exception as e:
                error_msg = str(e) if str(e) else "Unknown error occurred"
                print(f"  Error processing {email}: {error_msg}")
                error_count += 1

        print(f"\n{'DRY RUN ' if dry_run else ''}Summary:")
        print(f"  Successfully processed: {success_count}")
        print(f"  Errors: {error_count}")

        if dry_run:
            print("\nTo actually sync the data, run with --live flag")

        return success_count, error_count

    except Exception as e:
        print(f"Error during sync: {str(e)}")
        print(traceback.format_exc())
        return 0, 1


async def run_pipeline(dry_run=True):
    """
    Run the complete data pipeline

    Args:
        dry_run: If True, only show what would be done without making changes

    Returns:
        tuple: (success_count, error_count)
    """
    try:
        print("=" * 60)
        print("Scout Mailchimp Sync Pipeline")
        print("=" * 60)

        # Get credentials
        username = os.getenv("SCOUTBOOK_USERNAME")
        password = os.getenv("SCOUTBOOK_PASSWORD")
        headless = os.getenv("SCOUTBOOK_HEADLESS", "true").lower() == "true"

        if not username or not password:
            print("Error: Scoutbook credentials not found in .env file")
            print("Please set SCOUTBOOK_USERNAME and SCOUTBOOK_PASSWORD")
            return 0, 1

        # Step 1: Fetch data from Scoutbook
        print("\nStep 1: Fetching data from Scoutbook...")
        scraper = ScoutbookScraper()
        scoutbook_df = await scraper.fetch_scout_data_as_dataframe(
            username=username,
            password=password,
            headless=headless
        )

        if scoutbook_df.empty:
            print("Error: No data received from Scoutbook")
            return 0, 1

        print(f"Successfully fetched {len(scoutbook_df)} records from Scoutbook")

        # Step 2: Transform data
        print("\nStep 2: Transforming data...")
        transformed_df = transform_scout_data(scoutbook_df)

        if transformed_df.empty:
            print("Error: No data to process after transformation")
            return 0, 1

        # Step 3: Sync to Mailchimp
        print(f"\nStep 3: Syncing to Mailchimp...")
        success_count, error_count = sync_to_mailchimp(transformed_df, dry_run=dry_run)

        print("\n" + "=" * 60)
        print("Pipeline completed!")
        print(f"Successfully processed: {success_count} records")
        if error_count > 0:
            print(f"Errors: {error_count} records")
        print("=" * 60)

        return success_count, error_count

    except Exception as e:
        print(f"Pipeline failed: {str(e)}")
        print(traceback.format_exc())
        return 0, 1


async def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(
        description="Scout Mailchimp Sync - Scoutbook to Mailchimp Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scout_mailchimp_sync.py                 # Interactive mode
  python scout_mailchimp_sync.py --dry-run       # Dry run (default)
  python scout_mailchimp_sync.py --live          # Live sync to Mailchimp
        """
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help="Perform live sync to Mailchimp (default is dry run)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform dry run only (default behavior)"
    )

    args = parser.parse_args()

    # Determine dry run mode (default is True unless --live is specified)
    dry_run = not args.live

    # Run the pipeline
    success_count, error_count = await run_pipeline(dry_run=dry_run)

    # Exit with appropriate status code
    if error_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    # Check if required environment variables are set
    load_dotenv()

    required_vars = [
        "SCOUTBOOK_USERNAME",
        "SCOUTBOOK_PASSWORD",
        "MAILCHIMP_API_KEY",
        "MAILCHIMP_SERVER_PREFIX",
        "MAILCHIMP_AUDIENCE_ID",
    ]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print(f"Error: Missing required environment variables: {missing_vars}")
        print("Please check your .env file and ensure all credentials are set.")
        print("See .env.example for required variables.")
        sys.exit(1)

    # Run the main function
    asyncio.run(main())
