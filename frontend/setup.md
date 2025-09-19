# DE4 Forms Platform - Quick Setup Guide

## 🚀 Quick Start (5 minutes)

### 1. Install Dependencies
```bash
cd frontend
npm install
```

### 2. Start Development Server
```bash
npm start
```

### 3. Open in Browser
```
http://localhost:3000
```

### 4. Login with Demo Account
- **Username**: `admin`
- **Password**: `admin123`

## 🔧 Backend Connection

Make sure your backend is running on `http://localhost:8000` before starting the frontend.

If your backend runs on a different port, create a `.env` file:
```bash
echo "REACT_APP_API_URL=http://localhost:YOUR_PORT" > .env
```

## 📱 What You'll See

1. **Login Page** - Clean authentication interface
2. **Upload Page** - Drag-and-drop file upload
3. **Files Page** - AI editing with natural language
4. **Admin Dashboard** - System statistics and monitoring

## ✅ Verify Everything Works

1. **Health Check**: Dashboard should show green status
2. **Upload Test**: Try uploading an XML file
3. **AI Edit**: Test with prompt like "Add a new text field called 'notes'"
4. **Export**: Download the modified file

## 🎨 Features Included

- ✅ Modern, responsive design
- ✅ User authentication & session management
- ✅ File upload with drag-and-drop
- ✅ AI-powered form editing
- ✅ Admin dashboard with charts
- ✅ Real-time notifications
- ✅ Mobile-friendly interface

## 🚨 Troubleshooting

**Can't connect to backend?**
- Check backend is running on port 8000
- Verify CORS is configured correctly

**Login not working?**
- Use demo credentials: admin/admin123
- Check browser console for errors

**Upload failing?**
- Ensure you're logged in
- Check file format (XML/XLS only)
- Verify backend file upload endpoint

**Need help?** Check the full README.md for detailed documentation.
