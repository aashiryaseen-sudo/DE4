# XLSForm AI Editor | Builder

A powerful backend API for AI-powered XLSForm editing using natural language prompts. Built with FastAPI and LangGraph, this system allows you to upload XML forms and make complex edits through simple text commands.

## 🚀 Features

- **AI-Powered Editing**: Use natural language to edit XLSForm XML files
- **Dynamic Sheet Detection**: Automatically detects and works with any XML structure
- **Batch Operations**: Add multiple items in single operations
- **Task Management**: Cursor-like task breakdown for complex edits
- **RESTful API**: Clean, minimal API with Swagger documentation

## 📋 Requirements

- Python 3.8+
- OpenAI API key

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd DEs_Project
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   # Create .env file
   echo "OPENAI_API_KEY=your_openai_api_key_here" > .env
   ```

## 🚀 Quick Start

1. **Start the server**
   ```bash
   python main.py
   ```

2. **Access the API documentation**
   - Open your browser to `http://localhost:8000/docs`
   - Use the interactive Swagger UI to test endpoints

3. **Upload and edit a form**
   ```bash
   # Upload XML file
   POST /api/upload
   
   # Edit with AI
   POST /api/ai-edit
   {
     "prompt": "Add choices A, B, C to list MYLIST",
     "target_sheet": "select_one"
   }
   
   # Download modified file
   GET /api/export/xml
   ```

## 📚 API Endpoints

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload` | Upload and analyze XML file |
| `POST` | `/api/ai-edit` | AI-powered editing with prompts |
| `GET` | `/api/export/xml` | Download modified XML file |
| `GET` | `/api/status` | Get system status and history |

### Example Usage

#### Upload a Form
```bash
curl -X POST "http://localhost:8000/api/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_form.xml"
```

#### AI Edit with Prompt
```bash
curl -X POST "http://localhost:8000/api/ai-edit" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Add choices Option1, Option2, Option3 to list my_choices",
    "target_sheet": "select_one"
  }'
```

#### Download Modified File
```bash
curl -X GET "http://localhost:8000/api/export/xml" \
  --output modified_form.xml
```

## 🤖 AI Editing Examples

The AI can understand and execute various types of edits:

### Adding Choices
```
"Add choices A, B, C to list MYLIST"
"Add choice options Option1, Option2 to list customer_types"
```

### Adding Rows
```
"Add row with data X, Y, Z to settings sheet"
"Add new field with name 'test_field' and type 'text' to survey sheet"
```

### Complex Operations
```
"Remove all fields containing 'test' from survey sheet"
"Update the form title to 'New Survey 2025'"
"Add 5 new choice options to the equipment list"
```

## 🏗️ Architecture

```
├── main.py                 # FastAPI application
├── xml_parser.py          # XML parsing and analysis
├── xml_editor.py          # XML modification engine
├── langgraph_proper_agent.py  # AI agent with LangGraph
├── task_manager.py        # Task management system
├── models.py              # Pydantic data models
├── requirements.txt       # Dependencies
└── uploads/              # Uploaded files directory
```

## 🔧 Configuration

### Environment Variables
- `OPENAI_API_KEY`: Your OpenAI API key for AI functionality

### File Structure
- `uploads/`: Stores uploaded XML files
- `modified_*.xml`: Generated modified files with timestamps
- `*.json`: Data persistence files (auto-generated)

## 🧪 Testing

### Using Swagger UI
1. Start the server: `python main.py`
2. Go to `http://localhost:8000/docs`
3. Use the interactive interface to test all endpoints

### Using curl
```bash
# Test upload
curl -X POST "http://localhost:8000/api/upload" \
  -F "file=@test_form.xml"

# Test AI edit
curl -X POST "http://localhost:8000/api/ai-edit" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Add test choice to list test_list"}'

# Test export
curl -X GET "http://localhost:8000/api/export/xml" \
  --output result.xml
```

### Key Components
- **XLSFormParser**: Analyzes XML structure dynamically
- **XLSFormXMLEditor**: Applies modifications to XML
- **LangGraph Agent**: Processes natural language prompts
- **Task Manager**: Breaks complex operations into tasks

