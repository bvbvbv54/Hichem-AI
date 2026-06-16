# 🎯 Complete Image Generation Workflow

## Overview

The ImageFactory system now supports a complete end-to-end workflow:

```
1. Create Project
   ↓
2. Upload Excel (Products List)
   ↓
3. Auto-Generate Product Metadata
   ↓
4. Generate Images for All Products
   ↓
5. Download as Zip with Product Names
   ↓
6. Upload to Google Drive (Optional)
   ↓
7. Track Progress via Notifications
```

---

## Step 1: Create a Project

### Via Dashboard
1. Go to **Projects** tab
2. Click **+ New Project**
3. Enter project name (e.g., "Summer Collection 2026")
4. Add optional description
5. Click **Create**

### Via API
```bash
POST http://localhost:8000/api/v1/projects
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Summer Collection 2026",
  "description": "AI-generated product images for e-commerce"
}
```

**Response:**
```json
{
  "id": "proj_abc123",
  "name": "Summer Collection 2026",
  "status": "active",
  "created_at": "2026-06-13T18:35:00Z"
}
```

---

## Step 2: Upload Excel with Products

### Excel Format

Required columns:
- **URL** (or Link, Product URL, Product Link) - Product page URL
- Any additional columns (Title, Description, Category, etc.)

Example:

| URL | Title | Category | Price |
|-----|-------|----------|-------|
| https://example.com/product1 | Red Handbag | Accessories | $99.99 |
| https://example.com/product2 | Blue Shoes | Footwear | $79.99 |
| https://example.com/product3 | Black Jacket | Clothing | $149.99 |

### Upload via Dashboard
1. In project, click **Upload Products**
2. Select Excel file
3. Click **Upload**
4. System automatically extracts:
   - Product titles
   - Product descriptions
   - Existing product images for reference

### Upload via API
```bash
POST http://localhost:8000/api/v1/products/upload
Authorization: Bearer {token}
Content-Type: multipart/form-data

file: <your_file.xlsx>
project_id: proj_abc123
```

**Response:**
```json
{
  "batch_id": "batch_xyz789",
  "filename": "products.xlsx",
  "total_products": 3,
  "total_images_scraped": 12,
  "status": "parsed",
  "products": [
    {"url": "https://example.com/product1"},
    {"url": "https://example.com/product2"},
    {"url": "https://example.com/product3"}
  ],
  "message": "Found 3 products with 12 images. Configure generation settings below."
}
```

---

## Step 3: Project Products Auto-Update

After upload, the **Project Products** section automatically updates:

```
Project: Summer Collection 2026
├─ Product 1: Red Handbag
│  ├─ Status: Ready for Generation
│  ├─ Existing Images: 4
│  └─ URL: https://example.com/product1
├─ Product 2: Blue Shoes
│  ├─ Status: Ready for Generation
│  ├─ Existing Images: 3
│  └─ URL: https://example.com/product2
└─ Product 3: Black Jacket
   ├─ Status: Ready for Generation
   ├─ Existing Images: 5
   └─ URL: https://example.com/product3
```

### View Products via API
```bash
GET http://localhost:8000/api/v1/projects/proj_abc123/products
Authorization: Bearer {token}
```

---

## Step 4: Generate Images for All Products

### Configure Generation

Set parameters before starting:
- **Images per product:** 1-3 recommended
- **Image style:** (optional) "minimalist", "luxury", "lifestyle", etc.
- **Use Claude AI:** ✓ Recommended for enhanced prompts
- **Template:** (optional) Use predefined prompt templates

### Start Generation via Dashboard
1. Click **Generate Images** in project
2. Set number of images per product
3. Choose any additional options
4. Click **Start Generation**
5. Watch real-time progress

### Start Generation via API
```bash
POST http://localhost:8000/api/v1/products/generate
Authorization: Bearer {token}
Content-Type: application/json

{
  "batch_id": "batch_xyz789",
  "project_id": "proj_abc123",
  "num_images_per_product": 2,
  "image_descriptions": ["professional product photo", "lifestyle shot"],
  "use_claude": true
}
```

**Response:**
```json
{
  "batch_id": "batch_xyz789",
  "run_id": "run_abc123",
  "project_id": "proj_abc123",
  "total_images_to_generate": 6,
  "status": "processing",
  "estimated_duration_seconds": 120,
  "message": "Generation started for 3 products"
}
```

### Watch Real-Time Progress

The dashboard shows live updates:
```
Generation Progress
├─ Total: 6 images
├─ Completed: 2 ✅
├─ Processing: 1 ⏳
├─ Queued: 3 ⌛
└─ Failed: 0 ❌

Time Elapsed: 45 seconds
Estimated Time Remaining: 75 seconds

Product Status:
├─ Red Handbag: 2/2 completed ✅
├─ Blue Shoes: 1/2 completed ⏳
└─ Black Jacket: 0/2 queued ⌛
```

---

## Step 5: Download as Zip with Product Names

### Zip File Structure

When generation completes, the **Assets** section shows a download button for the zip:

```
summer_collection_2026_abc12345.zip
├─ Red_Handbag/
│  ├─ image_1.png
│  └─ image_2.png
├─ Blue_Shoes/
│  ├─ image_1.png
│  └─ image_2.png
└─ Black_Jacket/
   ├─ image_1.png
   └─ image_2.png
```

**Key Features:**
- ✅ Folders named exactly after product titles from Excel
- ✅ Images organized by product
- ✅ Zip named with run ID for easy identification
- ✅ Ready to use for e-commerce platforms

### Download via Dashboard
1. Go to **Assets** section
2. Find the run (e.g., "Summer Collection 2026 - 2026-06-13")
3. Click **Download Zip**
4. File downloads automatically

### Download via API
```bash
GET http://localhost:8000/api/v1/assets/runs/{run_id}/zip
Authorization: Bearer {token}

# Response: Downloads zip file with name format
# summer_collection_2026_abc12345.zip
```

### View Run Details
```bash
GET http://localhost:8000/api/v1/assets/runs/{run_id}
Authorization: Bearer {token}
```

**Response:**
```json
{
  "run_id": "run_abc123",
  "run_name": "Summer Collection 2026",
  "status": "completed",
  "products": [
    {
      "product_title": "Red Handbag",
      "product_url": "https://example.com/product1",
      "images": [
        {"id": "asset_1", "url": "s3://...", "path": "/app/outputs/..."}
      ]
    }
  ],
  "total_images": 6,
  "created_at": "2026-06-13T18:35:00Z",
  "completed_at": "2026-06-13T18:37:30Z"
}
```

---

## Step 6: Upload to Google Drive (Optional)

### Setup Google Drive Integration

1. **Get Google OAuth Credentials**
   - Go to https://console.cloud.google.com
   - Create OAuth 2.0 credentials
   - Note: Client ID, Client Secret, Redirect URI

2. **Configure in .env**
   ```bash
   GOOGLE_CLIENT_ID=your_client_id
   GOOGLE_CLIENT_SECRET=your_client_secret
   GOOGLE_REDIRECT_URI=http://localhost:3000/callback
   ```

3. **Connect Google Drive in Dashboard**
   - Go to **Settings** → **Google Drive**
   - Click **Connect to Google Drive**
   - Authenticate with your Google account
   - Grant permissions to ImageFactory
   - Confirm connection

### Upload Generation Results

After generation completes:

1. **Via Dashboard**
   - In Assets section, click **Upload to Drive** for the run
   - Select destination folder (or create new)
   - Click **Upload**
   - ✅ Confirmation shows when complete

2. **Via API**
   ```bash
   POST http://localhost:8000/api/v1/google-drive/upload/{run_id}
   Authorization: Bearer {token}
   
   ?project_name=Summer+Collection+2026
   ```

   **Response:**
   ```json
   {
     "success": true,
     "message": "Successfully uploaded to Google Drive",
     "upload": {
       "file_id": "gdrive_abc123",
       "file_link": "https://drive.google.com/file/d/gdrive_abc123/view",
       "folder_id": "folder_xyz789",
       "uploaded_at": "2026-06-13T18:40:00Z"
     }
   }
   ```

### Google Drive Structure

Files organized in Drive:
```
ImageFactory/
└─ Summer Collection 2026 - 2026-06-13
   └─ summer_collection_2026_abc12345.zip
      └─ [Contains all product folders with images]
```

---

## Step 7: Track Progress via Notifications

### Notification Types

The system automatically sends notifications for:

| Event | Notification | Example |
|-------|--------------|---------|
| **Generation Started** | ℹ️ Info | "Image generation started for 3 products" |
| **Product Complete** | ✅ Success | "Generated 2 images for Red Handbag" |
| **Generation Complete** | ✅ Success | "All images generated successfully" |
| **Generation Failed** | ❌ Error | "Failed to generate images for Blue Shoes" |
| **Upload to Drive** | ✅ Success | "Successfully uploaded to Google Drive" |
| **Storage Warning** | ⚠️ Warning | "Storage capacity at 85%" |

### View Notifications

**Via Dashboard**
1. Click **Notifications** tab (🔔)
2. See all recent events
3. Click notification to view details
4. Mark as read or delete

**Via API**
```bash
GET http://localhost:8000/api/v1/notifications?user_id=user_123
Authorization: Bearer {token}
```

**Response:**
```json
{
  "notifications": [
    {
      "id": "notif_1",
      "type": "generation_complete",
      "level": "success",
      "title": "Generation Complete",
      "message": "Successfully generated 6 images for Summer Collection",
      "created_at": "2026-06-13T18:37:30Z",
      "read": false,
      "data": {
        "run_id": "run_abc123",
        "project_id": "proj_abc123",
        "products_count": 3,
        "images_count": 6
      }
    },
    {
      "id": "notif_2",
      "type": "generation_started",
      "level": "info",
      "title": "Generation Started",
      "message": "Image generation started for 3 products",
      "created_at": "2026-06-13T18:35:00Z",
      "read": true
    }
  ],
  "total": 2
}
```

### Mark Notification as Read
```bash
POST http://localhost:8000/api/v1/notifications/{notification_id}/read
Authorization: Bearer {token}
```

---

## System Readiness Tracking

The dashboard continuously monitors system health:

**Components Tracked:**
- ✅ Backend API - REST server status
- ✅ Worker System - Celery task processing
- ✅ Message Queue - Redis job queue
- ✅ PostgreSQL DB - Database connection
- ✅ Redis Cache - Caching layer
- ✅ Asset Storage - File storage capability
- ✅ Delivery Backends - Output delivery systems
- ✅ AI Provider - Image generation API

**Dashboard Updates:**
- Real-time component health
- Automatic refresh every 5 seconds
- Warning indicators for issues
- Quick access to run smoke test

---

## Complete Workflow Example

### User Journey

```
1. Create Project: "Nike Summer 2026"
   ↓ (Project created with ID: proj_nike_123)

2. Upload Excel: 50 Nike products
   ↓ (System extracts 50 products with existing images)

3. Configure Generation:
   - 2 images per product
   - Use Claude for enhanced prompts
   ↓

4. Start Generation (100 images total)
   ↓
   Dashboard shows: 45 completed, 35 processing, 20 queued

5. Generation Completes ✅
   ↓
   Notification: "Generated 100 images for 50 products"

6. Download Zip
   ↓
   Get: nike_summer_2026_proj123.zip
   Contains: 50 folders with product names, 2 images each

7. Upload to Google Drive (Optional)
   ↓
   Notification: "Successfully uploaded to Google Drive"
   Files in Drive: ImageFactory/Nike Summer 2026 - ...

8. Use in E-Commerce
   ↓
   Import generated images to Shopify/WooCommerce/etc
```

---

## API Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/projects` | POST | Create project |
| `/api/v1/products/upload` | POST | Upload Excel |
| `/api/v1/projects/{id}/products` | GET | List project products |
| `/api/v1/products/generate` | POST | Start generation |
| `/api/v1/assets/runs` | GET | List generation runs |
| `/api/v1/assets/runs/{id}` | GET | Get run details |
| `/api/v1/assets/runs/{id}/zip` | GET | Download zip |
| `/api/v1/google-drive/auth-url` | GET | Get OAuth URL |
| `/api/v1/google-drive/upload/{run_id}` | POST | Upload to Drive |
| `/api/v1/notifications` | GET | Get notifications |
| `/api/v1/notifications/{id}/read` | POST | Mark read |

---

## Troubleshooting

### Generation Stops Unexpectedly
1. Check **Notifications** for error details
2. Check **System Readiness** for component issues
3. Verify API key for image provider
4. Check available storage space

### Images Not Generating
1. Verify AI provider credentials in .env
2. Check API rate limits
3. Ensure Claude API key is valid
4. Run smoke test to diagnose

### Zip Download Fails
1. Verify run is completed
2. Check storage has sufficient space
3. Ensure assets were generated
4. Try via API instead of dashboard

### Google Drive Upload Fails
1. Verify OAuth connection is active
2. Check if folder exists in Drive
3. Verify account has edit permissions
4. Try reconnecting Google Drive

---

## Next Steps

✅ System is ready!
1. Create your first project
2. Upload a test Excel file
3. Generate sample images
4. Download and preview results
5. Connect Google Drive for automatic uploads

**Start here:** http://localhost:3000/projects
