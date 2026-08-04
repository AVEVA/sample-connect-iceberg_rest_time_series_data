# CONNECT Query Timeseries Data Iceberg REST Flow

**Version:** 1.0.0

[![Build Status](https://dev.azure.com/AVEVA-VSTS/Cloud%20Platform/_apis/build/status%2Fproduct-readiness%2FAVEVA.sample-connect-iceberg_rest_time_series_data?repoName=AVEVA%2Fsample-connect-iceberg_rest_time_series_data&branchName=refs%2Fpull%2F1%2Fmerge)](https://dev.azure.com/AVEVA-VSTS/Cloud%20Platform/_build/latest?definitionId=24948&repoName=AVEVA%2Fsample-connect-iceberg_rest_time_series_data&branchName=refs%2Fpull%2F1%2Fmerge)

This notebook demonstrates zero-copy ecosystem consumption of CONNECT Virtual Tables through an open Iceberg-style flow.

The sections that follow provide a brief description of the process from beginning to end.

Developed against Python 3.14.2

## Running the sample

1. Clone the GitHub repository
1. Install required modules: `pip install -r requirements.txt`
1. Open the folder with your favorite IDE
1. Copy the output JSON of your Snowflake share to [appsettings.placeholder.json](appsettings.placeholder.json). Before editing, rename this file to `appsettings.json`. This repository's `.gitignore` rules should prevent the file from ever being checked in to any fork or branch, to ensure credentials are not compromised.
1. Run each code block and view the output. Once you get to step 2.5, modify the code block to choose your selected table from the previous table list (output from step 2.4) and specify whether the table is narrow or wide.

To Test the Sample:

1. Install pytest `python -m pip install pytest`
1. Run `python -m pytest -q`


## Configure the sample

Included in the sample there is an appsettings.example.json file with placeholders that need to be replaced with the proper values. They include information to connect to the iceberg REST endpoint made available by your Snowflake Share. The format of this file matches the format of the file downloaded when you create your share and download its connection information. You can copy and paste this information directly into the appsettings.json file.

The values to be replaced are in `appsettings.json`:

```json
{
  "qualifiedName": "YourQualifiedName_REPLACE_WITH_YOUR_VALUE",
  "bearerToken": "YourBearerToken_REPLACE_WITH_YOUR_TOKEN",
  "icebergEndpoint": "https://your-region.azuredatabricks.net/api/2.0/delta-sharing/metastores/YOUR_METASTORE_ID/iceberg"
}
```
---
 
For the main AVEVA samples page [ReadMe](https://github.com/AVEVA/AVEVA-Samples)