# So sánh nhãn người với quy tắc và critic (mẫu κ Traversal)

Đã gán: 100 dòng; nhãn người: {'STOP': 13, 'REJECT': 67, 'ACCEPT': 20}; dòng cần đáp án: 2.

| Nguồn | n | κ (3 lớp) | đồng ý | κ (đi / không đi) | κ bỏ dòng cần đáp án |
|---|---|---|---|---|---|
| trav-rule-v1 (nhãn tự động) | 100 | 0.569 | 0.73 | 0.545 | 0.561 |
| critic llm-deepseek-v4.1-flash | 100 | 0.392 | 0.67 | 0.471 | 0.392 |
| critic rule | 100 | 0.167 | 0.6 | 0.133 | 0.189 |

## Ma trận nhầm lẫn

- **trav-rule-v1 (nhãn tự động)**: nguoi=ACCEPT / ACCEPT: 20; nguoi=REJECT / ACCEPT: 20; nguoi=REJECT / REJECT: 40; nguoi=REJECT / STOP: 7; nguoi=STOP / STOP: 13
- **critic llm-deepseek-v4.1-flash**: nguoi=ACCEPT / ACCEPT: 17; nguoi=ACCEPT / REJECT: 3; nguoi=REJECT / ACCEPT: 17; nguoi=REJECT / REJECT: 46; nguoi=REJECT / STOP: 4; nguoi=STOP / ACCEPT: 2; nguoi=STOP / REJECT: 7; nguoi=STOP / STOP: 4
- **critic rule**: nguoi=ACCEPT / ACCEPT: 9; nguoi=ACCEPT / REJECT: 11; nguoi=REJECT / ACCEPT: 16; nguoi=REJECT / REJECT: 51; nguoi=STOP / ACCEPT: 7; nguoi=STOP / REJECT: 6

## Các dòng có ít nhất một nguồn lệch nhãn người

| id | câu hỏi | cạnh ứng viên | người | trav-rule-v1 (nhãn tự động) | critic llm-deepseek-v4.1-flash | critic rule | lý do quy tắc | ghi chú |
|---|---|---|---|---|---|---|---|---|
| t-5a8b120755-2-e40 | What country of origin does André Holland and 42 have in common? | Battle of Romanovka —participant→ United States | **STOP** | STOP | ≠ REJECT | ≠ REJECT | evidence_complete |  |
| t-5a84cb2555-1-e5305 | Which singer of the Bee Gees sung a middle part of a song in which the majority  | Robin Gibb —sibling→ Barry Gibb | **REJECT** | ≠ ACCEPT | REJECT | ≠ ACCEPT | evidence_on_path |  |
| t-5a89007355-3-e3941 | What Brooklyn-based rapper has worked with both Rafeal Casal and Mos Def? | Black Star (rap duo) —has part→ Talib Kweli | **STOP** | STOP | STOP | ≠ REJECT | evidence_complete |  |
| t-5a78d16455-1-e1628 | Between two scientists Ernst Messerschmid and Philippe Perrin, who is older? | Philippe Perrin —employer→ European Space Agency | **REJECT** | ≠ ACCEPT | REJECT | REJECT | evidence_on_path |  |
| t-5a75620455-1-e11932 | Which university was founded first, University of California, Berkeley or Saint  | Saint Louis University —founded by→ Most Reverend Louis Guillaume Valentin Dubourg | **REJECT** | ≠ ACCEPT | ≠ ACCEPT | ≠ ACCEPT | evidence_on_path |  |
| t-5a77300155-3-e2426 | Which TV series, written by the creators of Robocalypse, is set in Bikini Bottom | SpongeBob SquarePants —creator→ Stephen Hillenburg | **REJECT** | ≠ STOP | ≠ STOP | REJECT | evidence_complete |  |
| t-5a7b48b155-4-e8210 | These three apps that have similar functionality to Google for Education are com | Google for Education —has part→ Sheets | **ACCEPT** | ACCEPT | ACCEPT | ≠ REJECT | evidence_on_path |  |
| t-5a8ce15d55-0-e3046 | did Robert Wise have more award nominations than Zoltan Korda? | Robert Wise —director→ West Side Story | **REJECT** | ≠ ACCEPT | REJECT | REJECT | evidence_on_path |  |
| t-5a77300155-3-e2432 | Which TV series, written by the creators of Robocalypse, is set in Bikini Bottom | SpongeBob SquarePants —narrative location→ Bikini Bottom | **REJECT** | ≠ STOP | ≠ STOP | REJECT | evidence_complete |  |
| t-5a8b120755-2-e3887 | What country of origin does André Holland and 42 have in common? | The Sidehackers —country of origin→ United States | **STOP** | STOP | ≠ REJECT | ≠ ACCEPT | evidence_complete |  |
| t-5a78ce5d55-1-e4375 | The southernmost administrative region of Denmark is well-known for creating wha | Region Zealand —instance of→ administrative region | **ACCEPT** | ACCEPT | ≠ REJECT | ACCEPT | evidence_on_path |  |
| t-5ae1b53b55-5-e5627 | What Indian government tag was given to the handicraft known for making simple l | Gopalpur Tussar Fabrics —award received→ Geographical Indication tag | **REJECT** | ≠ ACCEPT | ≠ ACCEPT | ≠ ACCEPT | evidence_on_path | Hiểu chặt: chưa có câu định nghĩa shawl (đoạn Shawl). Cạnh GI lặp lại câu [2] đã đọc. |
| t-5ac1756355-2-e6886 | Who replaced the manager of the Aston Villa that began at Leeds United? | Martin O'Neill —replaces→ David O'Leary | **REJECT** | ≠ STOP | REJECT | REJECT | evidence_complete |  |
| t-5a77300155-3-e2467 | Which TV series, written by the creators of Robocalypse, is set in Bikini Bottom | SpongeBob SquarePants (season 3) —series→ SpongeBob SquarePants | **REJECT** | ≠ STOP | REJECT | ≠ ACCEPT | evidence_complete |  |
| t-5a7e618155-0-e6775 | New York State Route 9R rejoins its parent in a hamlet located  in what New York | New York State Route 9R —located in the administrative territorial entity→ Albany County | **ACCEPT** | ACCEPT | ≠ REJECT | ACCEPT | evidence_on_path | cạnh dẫn tới đáp án (quận của cả tuyến); chưa nói thẳng ấp nằm ở quận nào |
| t-5a8b120755-2-e2238 | What country of origin does André Holland and 42 have in common? | Lake Road (Western New York) —country→ United States | **STOP** | STOP | STOP | ≠ ACCEPT | evidence_complete |  |
| t-5a89007355-3-e3901 | What Brooklyn-based rapper has worked with both Rafeal Casal and Mos Def? | Black Star (rap duo) —founded by→ Talib Kweli | **STOP** | STOP | ≠ ACCEPT | ≠ REJECT | evidence_complete |  |
| t-5a72ba1a55-2-e9188 | Which song did Eminem and Rihanna collaborate on after their other collaboration | The Monster (song) —author→ Eminem | **ACCEPT** | ACCEPT | ACCEPT | ≠ REJECT | evidence_on_path | cạnh chỉ nói Eminem viết bài, chưa thấy Rihanna; nhận ra nhờ đáp án |
| t-5a8e8af555-1-e11884 | Which university is a private research university, University of California, Ber | University of California, Berkeley —part of→ University of California system | **REJECT** | ≠ ACCEPT | ≠ ACCEPT | ≠ ACCEPT | evidence_on_path |  |
| t-5a8c496555-1-e12114 | Which college was founded first, Williams College or University of Southern Cali | University of Southern California —inception→ 1880 | **ACCEPT** | ACCEPT | ACCEPT | ≠ REJECT | evidence_on_path |  |
| t-5a8fd9ac55-0-e7904 | Which feature film was released earlier, One Magic Christmas or Muppet Treasure  | One Magic Christmas —instance of→ film | **REJECT** | ≠ ACCEPT | ≠ ACCEPT | ≠ ACCEPT | evidence_on_path |  |
| t-5a8b120755-2-e4825 | What country of origin does André Holland and 42 have in common? | Belle Ayr Mine —country→ United States | **STOP** | STOP | ≠ REJECT | ≠ ACCEPT | evidence_complete |  |
| t-5ab7484c55-0-e7389 | Do James Schuyler and A. E. Housman have the same nationality? | James Schuyler —date of death→ April 12, 1991 | **REJECT** | ≠ ACCEPT | REJECT | REJECT | evidence_on_path |  |
| t-5ae1b53b55-4-e5626 | What Indian government tag was given to the handicraft known for making simple l | Gopalpur Tussar Fabrics —instance of→ Handicraft | **REJECT** | ≠ ACCEPT | REJECT | REJECT | evidence_on_path |  |
| t-5a8ce15d55-0-e3045 | did Robert Wise have more award nominations than Zoltan Korda? | Robert Wise —award received→ Academy Award for Best Picture | **ACCEPT** | ACCEPT | ≠ REJECT | ACCEPT | evidence_on_path |  |
| t-5a77300155-3-e2413 | Which TV series, written by the creators of Robocalypse, is set in Bikini Bottom | SpongeBob, You're Fired —series→ SpongeBob SquarePants | **REJECT** | ≠ STOP | REJECT | ≠ ACCEPT | evidence_complete |  |
| t-5ae7604155-2-e12457 | Which of the people that helped Max Hoffmann do defeat the Russia army was born  | Max Hoffmann —participant→ Erich Ludendorff | **ACCEPT** | ACCEPT | ACCEPT | ≠ REJECT | evidence_on_path |  |
| t-5a875b7555-1-e10935 | The song "Medicine" by The 1975 appears in a film directed by what Danish filmma | Drive (2011 film) —genre→ neo-noir crime film | **REJECT** | REJECT | ≠ ACCEPT | ≠ ACCEPT | not_evidence |  |
| t-5ac41b9e55-2-e3012 | what species of plants are Chamelaucium and Vanilla derived from? | Chamelaucium —has part→ Chamelaucium uncinatum | **STOP** | STOP | ≠ ACCEPT | ≠ ACCEPT | evidence_complete |  |
| t-5a8e0a0055-1-e1049 | Bordan Tkachuk was the CEO of a company that provides what sort of products? | Viglen —product or material produced→ servers | **REJECT** | REJECT | ≠ ACCEPT | REJECT | off_path | servers là ngõ cụt, chỉ là một sản phẩm cụ thể. Loại sản phẩm (CNTT) nằm ở đoạn văn Viglen, cần đọc đoạn (O8). Cách hiểu lỏng: khái quát từ các cạnh sản phẩm thì có thể ACCEPT. |
| t-5abbd58d55-2-e1686 | Are Cardinal Health and Kansas City Southern located in the same state? | Kansas City Southern (company) —instance of→ transportation holding company | **REJECT** | ≠ ACCEPT | REJECT | REJECT | evidence_on_path |  |
| t-5aba549f55-1-e9519 | What kind of song did Alexander Grant produce for Eminem? | Love the Way You Lie —instance of→ song | **REJECT** | ≠ ACCEPT | ≠ ACCEPT | ≠ ACCEPT | evidence_on_path |  |
| t-5a7f275d55-0-e7220 | Are both Jonathan Marray and Wayne Black British? | Jonathan Marray —award received→ Wimbledon Men's Doubles champion | **REJECT** | ≠ ACCEPT | ≠ ACCEPT | REJECT | evidence_on_path |  |
| t-5a843cf355-1-e2903 | What industry did both William Todd Field and Zoltan Korda work in? | Zoltan Korda —sibling→ Alexander Korda | **REJECT** | REJECT | ≠ ACCEPT | ≠ ACCEPT | off_path |  |
| t-5a89007355-3-e3938 | What Brooklyn-based rapper has worked with both Rafeal Casal and Mos Def? | Black Star (rap duo) —inception→ 1997 | **STOP** | STOP | STOP | ≠ REJECT | evidence_complete |  |
| t-5a84973e55-1-e2112 | Stockely Webster has paintings hanging in what home (that serves as the residenc | Gracie Mansion —located in or next to body of water→ Hell Gate | **REJECT** | REJECT | ≠ STOP | REJECT | off_path |  |
| t-5a8e4e7855-1-e8391 | Are both Papa John's Pizza and Papa Gino's specialized in Pizza? | Papa Gino's —headquarters location→ Dedham, Massachusetts | **REJECT** | ≠ ACCEPT | ≠ ACCEPT | REJECT | evidence_on_path |  |
| t-5a89382655-0-e10440 | Who served as the 1st Vice President of Colombia under El Libertador? | Francisco Antonio Zea —position held→ 1st Vice President of Colombia | **ACCEPT** | ACCEPT | ACCEPT | ≠ REJECT | evidence_on_path |  |
| t-5a8e0a0055-0-e1065 | Bordan Tkachuk was the CEO of a company that provides what sort of products? | Bordan Tkachuk —employer→ Viglen | **ACCEPT** | ACCEPT | ACCEPT | ≠ REJECT | evidence_on_path |  |
| t-5a72ba1a55-2-e9810 | Which song did Eminem and Rihanna collaborate on after their other collaboration | The Marshall Mathers LP 2 —producer→ Eminem | **REJECT** | REJECT | ≠ ACCEPT | REJECT | not_evidence |  |
| t-5adcf20f55-4-e10489 | Who directed the Hindi remake of the Korean film that starred Uhm Jung-hwa, Kim  | Te3n —director→ Ribhu Dasgupta | **ACCEPT** | ACCEPT | ACCEPT | ≠ REJECT | evidence_on_path |  |
| t-5a8f453855-1-e4010 | Dahlia and Aruncus are both examples of what type of plant catagorization? | Dahlia pinnata —parent taxon→ Dahlia | **REJECT** | REJECT | REJECT | ≠ ACCEPT | not_evidence |  |
| t-5a7b591155-3-e5635 |  What team does the oldest son play for, from the family whose middle son plays  | Eero Markkanen —member of sports team→ AIK | **REJECT** | REJECT | ≠ ACCEPT | ≠ ACCEPT | off_path | cần đáp án: câu hỏi có nhiều đội đúng (AIK, Dynamo Dresden, ĐTQG Phần Lan); đáp án chuẩn là ĐTQG (e5636 nằm ngay bên cạnh) |
| t-5ab7484c55-1-e7482 | Do James Schuyler and A. E. Housman have the same nationality? | A. E. Housman —notable work→ A Shropshire Lad | **REJECT** | ≠ ACCEPT | ≠ ACCEPT | REJECT | evidence_on_path |  |
| t-5a77300155-3-e2492 | Which TV series, written by the creators of Robocalypse, is set in Bikini Bottom | SpongeBob SquarePants —owned by→ MTV Networks | **REJECT** | ≠ STOP | ≠ STOP | REJECT | evidence_complete |  |
| t-5ab2b6fb55-0-e6616 | The arena in which the Adelaide Adrenaline play is also home to the world's firs | Adelaide Adrenaline —location→ Adelaide | **REJECT** | ≠ ACCEPT | REJECT | ≠ ACCEPT | evidence_on_path | có cạnh thẳng → Ice Arena (e6618); đi qua thành phố là đường vòng |
| t-5ae4843455-0-e8497 | Which club, founded in 1928, did Bob Johnson played for  | Bob Johnson (footballer, born 1905) —member of sports team→ Moor Ends Thorne | **REJECT** | REJECT | ≠ ACCEPT | REJECT | off_path |  |
| t-5abd920e55-0-e1693 | Were both Peter Duffell and Fred Niblo actors? | Peter Duffell —place of birth→ Canterbury | **REJECT** | ≠ ACCEPT | REJECT | REJECT | evidence_on_path |  |
| t-5abe765a55-1-e893 | Who has won more olympic medals: Angelique Kerber or Amélie Mauresmo? | Amélie Mauresmo —award received→ Grand Slam singles titles | **REJECT** | ≠ ACCEPT | REJECT | REJECT | evidence_on_path |  |
| t-5ac1756355-0-e6829 | Who replaced the manager of the Aston Villa that began at Leeds United? | David O'Leary —employer→ Aston Villa | **ACCEPT** | ACCEPT | ACCEPT | ≠ REJECT | evidence_on_path |  |
| t-5a8dfae555-0-e1415 | Cranium and Twin Tin Bots are both what? | Cranium (board game) —inception→ 1998 | **REJECT** | ≠ ACCEPT | REJECT | REJECT | evidence_on_path |  |
| t-5a8b120755-2-e3651 | What country of origin does André Holland and 42 have in common? | Ellicott City, Maryland —country→ United States | **STOP** | STOP | ≠ REJECT | ≠ ACCEPT | evidence_complete |  |
| t-5a82ebb855-0-e6158 | whats the famous bavagheet by arun date? | Arun Date —notable work→ Shukratara | **ACCEPT** | ACCEPT | ACCEPT | ≠ REJECT | evidence_on_path |  |
| t-5abbd58d55-2-e1689 | Are Cardinal Health and Kansas City Southern located in the same state? | Kansas City Southern (company) —subsidiary→ The Kansas City Southern Railway | **REJECT** | REJECT | REJECT | ≠ ACCEPT | not_evidence |  |
| t-5abd920e55-1-e1723 | Were both Peter Duffell and Fred Niblo actors? | Fred Niblo Jr. —father→ Fred Niblo | **REJECT** | REJECT | REJECT | ≠ ACCEPT | not_evidence |  |
| t-5a77919d55-1-e11825 | Who was born first, Marino Girolami or Daniel Myrick? | Daniel Myrick —date of birth→ September 3, 1963 | **ACCEPT** | ACCEPT | ACCEPT | ≠ REJECT | evidence_on_path |  |
| t-5a8b120755-2-e1873 | What country of origin does André Holland and 42 have in common? | Boogie2988 —country of citizenship→ United States | **STOP** | STOP | ≠ REJECT | ≠ ACCEPT | evidence_complete |  |
| t-5a8b120755-2-e3681 | What country of origin does André Holland and 42 have in common? | Cooperative Living Organization —country→ United States | **STOP** | STOP | ≠ REJECT | ≠ ACCEPT | evidence_complete |  |
| t-5aba549f55-0-e9188 | What kind of song did Alexander Grant produce for Eminem? | The Monster (song) —author→ Eminem | **REJECT** | REJECT | ≠ ACCEPT | REJECT | not_evidence |  |
| t-5ac41b9e55-3-e3012 | what species of plants are Chamelaucium and Vanilla derived from? | Chamelaucium —has part→ Chamelaucium uncinatum | **STOP** | STOP | STOP | ≠ REJECT | evidence_complete |  |
| t-5a7bb52355-0-e11245 | The song by English indie rock band Florence and the Machine written by Florence | What the Water Gave Me (song) —performer→ Florence and the Machine | **ACCEPT** | ACCEPT | ACCEPT | ≠ REJECT | evidence_on_path |  |
| t-5a7642f755-1-e8868 | who is younger Ulrich Walter or  Luca Parmitano? | Luca Parmitano —country of citizenship→ Italy | **REJECT** | ≠ ACCEPT | REJECT | REJECT | evidence_on_path |  |
| t-5aba549f55-1-e9528 | What kind of song did Alexander Grant produce for Eminem? | Love the Way You Lie —genre→ hip hop | **REJECT** | REJECT | ≠ ACCEPT | REJECT | off_path | hip hop chỉ là một phần đáp án (như dòng 41); chưa xác nhận nhà sản xuất, cạnh → Alex da Kid nằm ngay bên cạnh |
| t-5ae2e61455-0-e9027 | What is the inspirational source behind the name of this studio album by the Bri | The Crown Jewels —has part→ Queen (Queen album) | **REJECT** | ≠ ACCEPT | ≠ ACCEPT | ≠ ACCEPT | evidence_on_path |  |
| t-5a89007355-3-e3916 | What Brooklyn-based rapper has worked with both Rafeal Casal and Mos Def? | Definition —performer→ Black Star (rap duo) | **STOP** | STOP | ≠ REJECT | ≠ REJECT | evidence_complete |  |
| t-5a8dfae555-4-e1412 | Cranium and Twin Tin Bots are both what? | Cranium (board game) —instance of→ party game | **REJECT** | ≠ STOP | REJECT | REJECT | evidence_complete |  |
