from fasthtml.common import *
from utils.scraper import fetch_page, extract_main_content, html_to_xml, xml_to_html

# Add Monaco Editor
hdrs = (
    Script(src="https://cdn.tailwindcss.com"),
    Script(src="https://unpkg.com/monaco-editor@0.44.0/min/vs/loader.js"),
    Script("""
        require.config({ paths: { 'vs': 'https://unpkg.com/monaco-editor@0.44.0/min/vs' }});
        
        function initMonaco(xmlContent, htmlContent) {
            require(['vs/editor/editor.main'], function () {
                // XML Editor
                monaco.editor.create(document.getElementById('xml-editor'), {
                    value: xmlContent,
                    language: 'xml',
                    theme: 'vs-light',
                    readOnly: true,
                    wordWrap: 'on',
                    minimap: { enabled: false }
                });
                
                // HTML Editor
                monaco.editor.create(document.getElementById('html-editor'), {
                    value: htmlContent,
                    language: 'html',
                    theme: 'vs-light',
                    readOnly: true,
                    wordWrap: 'on',
                    minimap: { enabled: false }
                });
            });
        }
        
        function showTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('.tab-button').forEach(el => el.classList.remove('bg-blue-500', 'text-white'));
            
            document.getElementById(tabName).classList.remove('hidden');
            document.querySelector(`[onclick="showTab('${tabName}')"]`).classList.add('bg-blue-500', 'text-white');
        }
    """)
)

app, rt = fast_app(hdrs=hdrs, pico=False)

@rt('/')
def get():
    return Div(
        H1("FastHTML RAG Scraper", cls="text-3xl font-bold mb-6"),
        Form(
            Input(type="text", name="url", placeholder="Enter FastHTML docs URL", 
                  value="https://fastht.ml/docs/", cls="w-full p-2 border rounded mb-4"),
            Button("Scrape", type="submit", cls="bg-blue-500 text-white px-4 py-2 rounded"),
            method="post", action="/scrape"
        ),
        cls="max-w-4xl lg:max-w-6xl xl:max-w-7xl 2xl:max-w-full mx-auto p-6"
    )

@rt('/scrape')
def post(url: str):
    try:
        # Scrape the content
        soup = fetch_page(url)
        main_content = extract_main_content(soup)
        xml_content = html_to_xml(main_content, url)
        converted_html = xml_to_html(xml_content)
        
        return Div(
            H1("Scraping Results", cls="text-3xl font-bold mb-6"),
            Div(
                # Left side - XML Content
                Div(
                    H2("XML Content", cls="text-xl font-semibold mb-2"),
                    Div(id="xml-editor", cls="border rounded", style="height: 80vh;"),
                    cls="w-full md:w-1/2 pr-0 md:pr-2 mb-4 md:mb-0"
                ),
                # Right side - Tabbed content
                Div(
                    # Tab buttons
                    Div(
                        Button("Converted HTML", 
                               onclick="showTab('converted-tab')", 
                               cls="tab-button px-4 py-2 bg-blue-500 text-white rounded-t border-b-2 border-blue-500"),
                        Button("Raw HTML", 
                               onclick="showTab('raw-tab')", 
                               cls="tab-button px-4 py-2 bg-gray-200 text-gray-700 rounded-t border-b-2 border-gray-300"),
                        cls="flex"
                    ),
                    # Tab contents
                    Div(
                        # Converted HTML tab (default)
                        Div(
                            Div(id="html-editor", cls="border rounded-b", style="height: 75vh;"),
                            id="converted-tab", cls="tab-content"
                        ),
                        # Raw HTML tab
                        Div(
                            Pre(Code(main_content.prettify(), cls="language-markup"), 
                                cls="bg-gray-100 p-4 rounded-b overflow-auto max-h-[75vh]"),
                            id="raw-tab", cls="tab-content hidden"
                        ),
                        cls="border border-gray-300 rounded-b"
                    ),
                    cls="w-full md:w-1/2 pl-0 md:pl-2"
                ),
                cls="flex flex-col md:flex-row gap-4"
            ),
            A("Back", href="/", cls="inline-block mt-4 bg-gray-500 text-white px-4 py-2 rounded"),
            Script(f"setTimeout(() => initMonaco({repr(xml_content)}, {repr(converted_html)}), 100);"),
            cls="max-w-4xl lg:max-w-6xl xl:max-w-7xl 2xl:max-w-full mx-auto p-6"
        )
    except Exception as e:
        return Div(
            H1("Error", cls="text-3xl font-bold mb-6 text-red-600"),
            P(f"Failed to scrape URL: {str(e)}", cls="text-red-500"),
            A("Back", href="/", cls="inline-block mt-4 bg-gray-500 text-white px-4 py-2 rounded"),
            cls="max-w-6xl mx-auto p-6"
        )

serve()
