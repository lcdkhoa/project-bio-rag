\NeedsTeXFormat{LaTeX2e}

\providecommand{\baseclass}{book}
\newcommand{\classname}{thesis}
\ProvidesClass{\classname}[2023/12/23 v1.0 Thesis]

\DeclareOption*{\PassOptionsToClass{\CurrentOption}{\baseclass}}
\ProcessOptions\relax
\PassOptionsToClass{a4paper,openany}{\baseclass}
\LoadClass{\baseclass}


%=========================== Typography ==========================%
\RequirePackage[utf8]{vietnam}
\RequirePackage[utf8]{inputenc}

% Font Times New Roman
\renewcommand{\rmdefault}{ptm}

% Kích thước chữ chuẩn 13pt & Dãn dòng 1.5 lines
\renewcommand{\normalsize}{\fontsize{13pt}{19.5pt}\selectfont}
\normalsize
\linespread{1.3} % Dãn dòng 1.5 lines theo chuẩn học thuật (13pt x 1.5)

%========================= Công thức Hoá =========================%
% `\ce{CO2}` -> CO2 với chỉ số dưới đúng chuẩn. Cần cho Chương 3 và 4:
% chính chỉ số dưới là chỗ OCR làm hỏng nhiều nhất (xem phần bàn luận).
\RequirePackage[version=4]{mhchem}


%============================= Images ============================%
\RequirePackage{graphicx}
\RequirePackage{subcaption}


%============================= Tables ============================%
\RequirePackage{threeparttable}
\RequirePackage{makecell}
\RequirePackage{multirow}
\RequirePackage{longtable}
\RequirePackage{booktabs}
\RequirePackage{tabularx}
\RequirePackage{rotating} % Hỗ trợ bảng xoay ngang (đầu bảng quay sang lề trái)


%============================ Drawing ============================%
\RequirePackage{tikz}
\usetikzlibrary{calc, shapes.geometric}


%========================= Page & Layout ==========================%
% Quy định lề: Lề trên 3cm, lề dưới 3.5cm, lề trái 3.5cm, lề phải 2cm
\RequirePackage{geometry}
\geometry{
    paper=a4paper,
    top=3.0cm,
    bottom=3.5cm,
    left=3.5cm,
    right=2.0cm,
    headheight=16pt,
    bindingoffset=0cm,
}


\RequirePackage{fancyhdr}


%============================ Colors =============================%
\RequirePackage{xcolor}
\definecolor{blue}{HTML}{3F63B1}


%======================= Maths & Algorithms =======================%
\RequirePackage{amsmath}
\RequirePackage{amssymb}

\RequirePackage{algorithm}
\RequirePackage[linesnumbered,ruled,vlined,algo2e]{algorithm2e}

\SetKwInput{KwInput}{Input}
\SetKwInput{KwOutput}{Output}
\SetKwInput{KwInit}{Init}
\SetKwProg{Fn}{Function}{:}{end}

%==================== Cites, Links & References ===================%
\RequirePackage[
    backend=biber,
    style=ieee,
    sorting=author_title_venue_year
]{biblatex}
\addbibresource{src/references.bib}
\BiblatexSplitbibDefernumbersWarningOff

% Định nghĩa sơ đồ sắp xếp theo chuẩn trường:
% 1. presort (phân tách Tiếng Việt / Tiếng Anh)
% 2. sortkey (xếp theo Tên tác giả Việt Nam hoặc khoá tuỳ chỉnh)
% 3. Tên tác giả (Author/Editor)
% 4. Tựa đề tài liệu (Title)
% 5. Nơi công bố / Tạp chí / Nhà xuất bản (Venue/Journal/Publisher/Location)
% 6. Năm phát hành (Year)
\DeclareSortingTemplate{author_title_venue_year}{
  \sort{
    \field{presort}
  }
  \sort[final]{
    \field{sortkey}
  }
  \sort{
    \field{sortname}
    \field{author}
    \field{editor}
    \field{translator}
    \field{sorttitle}
    \field{title}
  }
  \sort{
    \field{sorttitle}
    \field{title}
  }
  \sort{
    \field{journaltitle}
    \field{booktitle}
    \field{series}
    \field{publisher}
    \field{location}
  }
  \sort{
    \field{sortyear}
    \field{year}
  }
}

% Tách danh mục: Tiếng Việt (presort = a) xếp trước, Tiếng Anh (presort = z) xếp sau
\DeclareSourcemap{
  \maps[datatype=bibtex]{
    \map{
      \step[fieldsource=keywords, match=tiengviet, final]
      \step[fieldset=presort, fieldvalue={a}]
    }
    \map{
      \step[fieldsource=keywords, notmatch=tiengviet, final]
      \step[fieldset=presort, fieldvalue={z}]
    }
  }
}

\RequirePackage[hidelinks, unicode]{hyperref}


%======================= Headings & captions ======================%
\renewcommand{\chaptername}{Chương}

\RequirePackage{titlesec}

% Đánh số mục và tiểu mục: 3 cấp số Ả-rập phân cách bằng dấu chấm (3.1., 3.1.1., ...)
\setcounter{secnumdepth}{3}
\setcounter{tocdepth}{3}
\renewcommand{\thesection}{\thechapter.\arabic{section}.}
\renewcommand{\thesubsection}{\thechapter.\arabic{section}.\arabic{subsection}.}
\renewcommand{\thesubsubsection}{\thechapter.\arabic{section}.\arabic{subsection}.\arabic{subsubsection}.}

% Định dạng tiêu đề theo chuẩn:
% Chương 3 ... (bold, font 14)
\titleformat{\chapter}[hang]
  {\normalfont\fontsize{14pt}{18pt}\selectfont\bfseries}
  {\chaptertitlename\ \thechapter:\ }
  {0pt}
  {\fontsize{14pt}{18pt}\selectfont\bfseries}
\titleformat{name=\chapter,numberless}[hang]
  {\normalfont\fontsize{14pt}{18pt}\selectfont\bfseries\centering}
  {}
  {0pt}
  {\fontsize{14pt}{18pt}\selectfont\bfseries}
\titlespacing*{\chapter}{0pt}{18pt}{14pt}

% 3.1. ... (bold, font 13)
\titleformat{\section}
  {\normalfont\fontsize{13pt}{17pt}\selectfont\bfseries}
  {\thesection\ }
  {0pt}
  {\fontsize{13pt}{17pt}\selectfont\bfseries}
\titlespacing*{\section}{0pt}{12pt}{6pt}

% 3.1.1. ... (bold, font 13)
\titleformat{\subsection}
  {\normalfont\fontsize{13pt}{17pt}\selectfont\bfseries}
  {\thesubsection\ }
  {0pt}
  {\fontsize{13pt}{17pt}\selectfont\bfseries}
\titlespacing*{\subsection}{0pt}{10pt}{4pt}

% 3.1.1.1. ... (bold, font 13)
\titleformat{\subsubsection}
  {\normalfont\fontsize{13pt}{17pt}\selectfont\bfseries}
  {\thesubsubsection\ }
  {0pt}
  {\fontsize{13pt}{17pt}\selectfont\bfseries}
\titlespacing*{\subsubsection}{0pt}{8pt}{3pt}

% Caption hình ảnh và bảng biểu: nhãn in đậm, font chú thích rõ ràng
\RequirePackage[labelfont=bf, font=small]{caption}

% Lệnh đưa mục vào TOC mà không hiển thị số trang (dành cho phần đầu không đánh số)
\newcommand{\addchapternopage}[1]{%
  \addtocontents{toc}{\protect\contentsline{chapter}{\textbf{#1}}{}{}}%
}


%============================ Others =============================%
\RequirePackage{float}
\RequirePackage{adjustbox}


\newcommand{\abbrevname}{DANH MỤC TỪ VIẾT TẮT}
\NewDocumentEnvironment{abbreviations}{ m }{%
	\begin{longtable}{#1}
	}{%
	\end{longtable}
	\addtocounter{table}{-1}% Don't count this table as one of the document tables
}

\newcommand{\transname}{DANH MỤC TỪ TẠM DỊCH}
\NewDocumentEnvironment{translatetion}{ m }{%
	\begin{longtable}{#1}
	}{%
	\end{longtable}
	\addtocounter{table}{-1}% Don't count this table as one of the document tables
}
