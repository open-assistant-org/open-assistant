# Nextcloud Platform Integration

This guide covers integrating with Nextcloud for file storage and access via WebDAV.

## Overview

Nextcloud integration provides access to files stored in your self-hosted or managed Nextcloud instance.

**Capabilities**:
- List files and folders
- Read file contents
- Search for files
- Download files

## Prerequisites

- Nextcloud instance (self-hosted or managed)
- Nextcloud account with file access
- App password (recommended over main password)

## Step 1: Create App Password

For security, use an app-specific password instead of your main Nextcloud password.

1. Log in to your Nextcloud instance
2. Go to **Settings > Personal > Security**
3. Scroll to **Devices & sessions**
4. Enter app name: "Open Assistant"
5. Click **Create new app password**
6. Copy the generated password

## Step 2: Get WebDAV URL

Your Nextcloud WebDAV URL follows this pattern:

```
https://your-nextcloud-instance.com/remote.php/dav/files/USERNAME/
```

Replace:
- `your-nextcloud-instance.com` with your Nextcloud domain
- `USERNAME` with your Nextcloud username

**Example**:
```
https://cloud.example.com/remote.php/dav/files/john/
```

## Step 3: Configure Application

Configuration is managed through the Settings UI or environment variables (see below). There is no `config.yaml` file — all settings are stored in the database.

Or use environment variables:

```bash
NEXTCLOUD_URL=https://cloud.example.com
NEXTCLOUD_USERNAME=john
NEXTCLOUD_PASSWORD=your-app-password
```

## Step 4: Test Connection

Test the Nextcloud connection using the **Test Connection** button in **Settings > Integrations > Nextcloud**, or via the API:

```bash
POST /api/integrations/test-connection
```

With body: `{"service_name": "nextcloud"}`

## Operations

### List Files

```python
# List files in default folder
files = nextcloud_agent.list_files()

# List files in specific folder
files = nextcloud_agent.list_files(
    folder_path="/Photos"
)

# List root directory
files = nextcloud_agent.list_files(
    folder_path="/"
)
```

**Response**:
```python
[
    {
        "name": "document.pdf",
        "path": "/Documents/document.pdf",
        "type": "file",
        "size": 1024576,
        "modified": "2024-01-15T10:30:00Z"
    },
    {
        "name": "Folder",
        "path": "/Documents/Folder",
        "type": "directory",
        "modified": "2024-01-10T14:20:00Z"
    }
]
```

### Read File

```python
# Read file content
content = nextcloud_agent.read_file(
    file_path="/Documents/notes.txt"
)

# Read file as bytes
content_bytes = nextcloud_agent.read_file_bytes(
    file_path="/Documents/image.png"
)
```

### Download File

```python
# Download file to local storage
nextcloud_agent.download_file(
    remote_path="/Documents/report.pdf",
    local_path="./downloads/report.pdf"
)
```

### Search Files

```python
# Search for files by name
files = nextcloud_agent.search_files(
    query="invoice"
)

# Search in specific folder
files = nextcloud_agent.search_files(
    query="*.pdf",
    folder_path="/Documents"
)
```

### Get File Info

```python
# Get file metadata
info = nextcloud_agent.get_file_info(
    file_path="/Documents/document.pdf"
)
```

**Response**:
```python
{
    "name": "document.pdf",
    "path": "/Documents/document.pdf",
    "size": 1024576,
    "type": "file",
    "mime_type": "application/pdf",
    "modified": "2024-01-15T10:30:00Z",
    "created": "2024-01-10T09:00:00Z",
    "etag": "abc123..."
}
```

### Upload File

```python
# Upload file content
nextcloud_agent.upload_file(
    remote_path="/Documents/new_file.txt",
    content=b"Hello, world!"
)

# Upload from local file path
nextcloud_agent.upload_file(
    remote_path="/Documents/report.pdf",
    source_path="./local_report.pdf"
)
```

### Create Folder

```python
# Create a new folder
nextcloud_agent.create_folder(
    folder_path="/Documents/Projects"
)
```

### Delete File or Folder

```python
# Delete a file or folder
nextcloud_agent.delete_file(
    file_path="/Documents/old_file.txt"
)
```

### Move / Rename

```python
# Move or rename a file
nextcloud_agent.move_file(
    source_path="/Documents/old_name.txt",
    destination_path="/Documents/new_name.txt"
)
```

### Copy File

```python
# Copy a file to a new location
nextcloud_agent.copy_file(
    source_path="/Documents original.txt",
    destination_path="/Documents/backup.txt"
)
```

## WebDAV Details

Nextcloud uses the WebDAV protocol for file access.

**Base URL Structure**:
```
https://[server]/remote.php/dav/files/[username]/[path]
```

**Authentication**:
- Basic HTTP authentication
- Username + app password

**Supported Operations**:
- `PROPFIND` - List files and properties
- `GET` - Download files
- `HEAD` - Get file metadata

## Troubleshooting

### Common Errors

**Error: `Connection refused`**
- Solution: Verify server URL is correct
- Check that Nextcloud is accessible
- Test URL in browser first

**Error: `401 Unauthorized`**
- Solution: Verify username and password
- Regenerate app password
- Check that account has file access

**Error: `404 Not Found`**
- Solution: Verify WebDAV path is correct
- Check that file/folder exists
- Ensure path starts with `/`

**Error: `SSL Certificate verification failed`**
- Solution: If using self-signed certificate, set `verify_ssl: false` (not recommended for production)
- Better: Add certificate to trusted store

### Connection Issues

**Cannot connect to server**:
1. Test server URL in browser
2. Check firewall rules
3. Verify network connectivity
4. Check Nextcloud is running

**Authentication fails**:
1. Regenerate app password
2. Verify username is correct
3. Check account isn't locked
4. Test credentials in browser

### File Access Issues

**Cannot see files**:
- Verify folder path is correct
- Check file permissions
- Ensure folder exists
- Test with root folder first

**Cannot read files**:
- Check file permissions
- Verify file isn't locked
- Check disk space
- Test with small text file first

## Performance Considerations

### Caching

Implement caching for:
- File listings (cache for 5-10 minutes)
- File metadata (cache until modified)
- Search results (cache for 2-3 minutes)

### Rate Limiting

While Nextcloud doesn't have strict API limits, be considerate:
- Implement delays between requests
- Batch operations where possible
- Cache frequently accessed data

### Large Files

For large files:
- Stream downloads instead of loading into memory
- Implement progress tracking
- Consider chunked transfers
- Set appropriate timeouts

## Security Best Practices

1. **Authentication**:
   - Always use app passwords
   - Never store main password
   - Rotate passwords regularly
   - Use unique passwords per app

2. **SSL/TLS**:
   - Always use HTTPS
   - Verify SSL certificates
   - Avoid self-signed certs in production
   - Keep certificates up to date

3. **Access Control**:
   - Grant minimum required permissions
   - Use separate accounts for different purposes
   - Monitor access logs
   - Revoke unused app passwords

4. **Data Protection**:
   - Encrypt credentials at rest
   - Use environment variables
   - Restrict file permissions (600)
   - Never commit credentials

## WebDAV Client Library

The integration uses `webdavclient3` Python library.

**Key Features**:
- Full WebDAV protocol support
- SSL/TLS support
- Proxy support
- Async operations (with proper implementation)

**Installation**:
```bash
pip install webdavclient3
```

**Configuration**:
```python
from webdav3.client import Client

client = Client({
    'webdav_hostname': 'https://cloud.example.com',
    'webdav_login': 'username',
    'webdav_password': 'app-password',
    'webdav_root': '/remote.php/dav/files/username/'
})
```

## Alternative Nextcloud APIs

While this integration uses WebDAV, Nextcloud also provides:

- **OCS API**: For shares, users, groups
- **REST API**: For some app-specific functions
- **Talk API**: For Nextcloud Talk integration

These are not currently implemented but could be added in the future.

## Limitations

Current limitations:
- No file versioning support
- No sharing functionality
- No trash/restore support

These limitations are by design for safety in personal assistant use case.

## Related Documentation

- [Solution Architecture](../architecture/solution-architecture.md) - Technology details
- [Software Architecture](../architecture/software-architecture.md) - Integration implementation
- [Configuration Guide](../setup/configuration.md) - Configuration options

## External References

- [Nextcloud WebDAV Documentation](https://docs.nextcloud.com/server/latest/user_manual/en/files/access_webdav.html)
- [webdavclient3 Documentation](https://github.com/ezhov-evgeny/webdav-client-python-3)
- [WebDAV Protocol](https://tools.ietf.org/html/rfc4918)
