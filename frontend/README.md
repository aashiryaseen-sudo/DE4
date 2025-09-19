# DE4 Forms Platform - Frontend

A modern, responsive React application for the DE4 Forms Platform, providing a sleek interface for XML form management with AI-powered editing capabilities.

## 🚀 Features

- **User Authentication** - Secure login/registration system
- **File Upload & Management** - Drag-and-drop XML/XLS file upload
- **AI-Powered Editing** - Natural language form editing
- **Admin Dashboard** - Comprehensive system monitoring and management
- **Responsive Design** - Works perfectly on desktop and mobile devices
- **Real-time Notifications** - Toast notifications for user feedback
- **Modern UI** - Clean, professional interface with Tailwind CSS

## 🛠️ Tech Stack

- **React 18** - Modern React with hooks
- **React Router v6** - Client-side routing
- **Tailwind CSS** - Utility-first CSS framework
- **Axios** - HTTP client for API requests
- **React Hot Toast** - Beautiful notifications
- **Lucide React** - Beautiful, customizable icons
- **Recharts** - Responsive charts for admin dashboard
- **Headless UI** - Unstyled, accessible UI components

## 📦 Installation

1. **Navigate to frontend directory**:
   ```bash
   cd frontend
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

3. **Start development server**:
   ```bash
   npm start
   ```

4. **Open in browser**:
   ```
   http://localhost:3000
   ```

## 🔧 Configuration

The app automatically connects to the backend API running on `http://localhost:8000`. If your backend runs on a different port, update the `REACT_APP_API_URL` environment variable.

Create a `.env` file in the frontend directory:
```env
REACT_APP_API_URL=http://localhost:8000
```

## 📱 Pages & Features

### Authentication
- **Login Page** (`/login`) - User authentication with demo credentials
- **Register Page** (`/register`) - New user account creation

### File Operations
- **Upload Page** (`/upload`) - File upload with drag-and-drop support
- **Files Page** (`/files`) - AI editing interface with history tracking

### Admin Panel
- **Admin Dashboard** (`/admin`) - System overview with:
  - User statistics and active sessions
  - Form management overview
  - Customization requests tracking
  - Operations audit log
  - Interactive charts and visualizations

## 🎨 Design System

### Colors
- **Primary**: Blue (`#3B82F6`)
- **Success**: Green (`#10B981`)
- **Warning**: Yellow (`#F59E0B`)
- **Error**: Red (`#EF4444`)
- **Gray Scale**: Modern gray palette

### Components
- **Cards**: Clean white containers with subtle shadows
- **Buttons**: Primary, secondary, and danger variants
- **Forms**: Consistent input styling with validation
- **Badges**: Status indicators with color coding
- **Tables**: Responsive data tables with proper spacing

## 🔐 Authentication Flow

1. User logs in with credentials
2. Backend returns session token and user data
3. Token stored in localStorage
4. Axios interceptor adds token to all requests
5. Protected routes check authentication status
6. Admin routes check user role permissions

## 📊 Admin Dashboard Features

### Real-time Statistics
- Total users and active sessions
- Master forms and versions
- Customization requests status
- Operations success rate

### Interactive Charts
- Operations success/failure pie chart
- Requests status breakdown
- Performance metrics visualization

### Data Tables
- Recent master forms with metadata
- Active user sessions monitoring
- Customization requests tracking
- Operations audit log with filtering

## 🚦 API Integration

### Endpoints Used
- `POST /api/users/register` - User registration
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `GET /api/health` - System health check
- `POST /api/upload` - File upload
- `POST /api/ai-edit` - AI-powered editing
- `GET /api/export/xml` - File export
- `GET /api/status` - File status
- `GET /api/admin/dashboard` - Admin dashboard data

### Error Handling
- Automatic token refresh
- Session expiration handling
- User-friendly error messages
- Network error recovery

## 🎯 User Experience

### Navigation
- Clean, intuitive navigation bar
- Role-based menu items
- Active page highlighting
- Mobile-responsive design

### Feedback
- Loading states for all operations
- Success/error notifications
- Progress indicators
- Validation messages

### Accessibility
- Proper ARIA labels
- Keyboard navigation support
- Screen reader compatibility
- High contrast design

## 🔧 Development

### Available Scripts
- `npm start` - Start development server
- `npm build` - Build for production
- `npm test` - Run test suite
- `npm eject` - Eject from Create React App

### Project Structure
```
src/
├── components/          # Reusable components
│   ├── Layout/         # Layout components
│   └── ProtectedRoute.js
├── contexts/           # React contexts
│   └── AuthContext.js  # Authentication context
├── pages/              # Page components
│   ├── auth/          # Authentication pages
│   ├── admin/         # Admin pages
│   ├── Upload.js      # File upload
│   └── Files.js       # File management
├── services/          # API services
│   └── api.js         # Axios configuration
├── App.js             # Main app component
├── index.js           # Entry point
└── index.css          # Global styles
```

## 🚀 Production Build

1. **Build the app**:
   ```bash
   npm run build
   ```

2. **Serve static files**:
   ```bash
   npx serve -s build
   ```

3. **Deploy**: Upload the `build` folder to your web server

## 🔗 Backend Integration

This frontend is designed to work seamlessly with the DE4 Forms Platform backend. Ensure the backend is running before starting the frontend development server.

### Required Backend Endpoints
- All authentication endpoints
- File upload/management endpoints  
- Admin dashboard data endpoints
- Health check endpoints

## 📝 Demo Credentials

For testing purposes, use these credentials:
- **Username**: `admin`
- **Password**: `admin123`
- **Role**: Administrator (full access)

## 🐛 Troubleshooting

### Common Issues
1. **CORS errors**: Ensure backend allows frontend origin
2. **API connection**: Check backend is running on correct port
3. **Authentication issues**: Clear localStorage and try again
4. **Build errors**: Delete `node_modules` and reinstall

### Development Tips
- Use browser dev tools for debugging
- Check network tab for API calls
- Use React DevTools extension
- Enable hot reloading for faster development

## 📄 License

This project is part of the DE4 Forms Platform and follows the same licensing terms.
