# Kanıt Kontrol

Seçtiğiniz dosyaların mevcut JSON/SHA256 kataloğuyla aynı olup olmadığını Türkçe gösteren küçük, çevrimdışı bir araçtır. Dosyaları değiştirmez. Python 3.10 veya üzeri yeterlidir; ek paket, hesap, sunucu veya API anahtarı gerekmez.

## Kullanım

ChatGPT veya Codex'te eklentiyi seçip manifesti ve ilgili dosyaları sağlayın. Python ve dosya erişimi bulunan hostta dahil beceri kontrolü çalıştırır. Bu yetenekler bulunmayan hostta eksik girdi açıkça belirtilir.

Yerel komut satırı:

    python skills/kanit-kontrol/scripts/kanit_kontrol.py MANIFEST.json --root DOSYA_KLASORU

Makine tarafından okunabilir JSON çıktı için --json; İngilizce çıktı için --lang en eklenir. Varsayılan dil Türkçedir.

## Manifest

files dizisi boş olmamalıdır. Her kayıtta klasör içindeki göreli POSIX path ve 64 hex karakterli sha256 bulunur. bytes alanı verilirse negatif olmayan tamsayı olmalıdır. Katalogdaki ek açıklama alanları kullanılabilir.

    {
      "files": [
        {
          "path": "abc.txt",
          "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
          "bytes": 3
        }
      ]
    }

Bu örnek, tam olarak abc içeren ve sonunda satır sonu bulunmayan üç baytlık dosyanın bilinen SHA256 vektörüdür.

Dosyalar ham baytlarıyla kontrol edilir; CRLF ve LF kendiliğinden aynı sayılmaz. Mutlak yollar, seçilen klasör dışına kaçan yollar, geçersiz veri ve yinelenen kayıtlar hata olarak bildirilir. Manifest içindeki root alanı seçilen çalışma klasörünü değiştirmez.

## Sonuç

- 0 / OK: Listelenen dosyalar eşleşti.
- 1 / FAILED: Eksik, değişmiş, boyutu farklı veya okunamayan dosya var.
- 2 / INVALID: Manifest, yol, veri biçimi veya komut hatası var.

JSON raporunda status, message, summary ve files alanları bulunur. SHA256 eşleşmesi yalnız dosya bütünlüğünü gösterir; kaynak incelemesi, davranış kabulü veya yayın onayı değildir.

## Testler

    python -m unittest discover -s tests -p "*oracle.py" -v

Dondurulmuş davranış oracle'ı, gerçek ayrı CLI süreçleriyle yapılan tamamlayıcı uçtan uca kontrollerden ayrı korunur. Testler geçici örnek dosyalar kullanır.

## Mevcut araçlarla ilişki

[GNU sha256sum](https://www.gnu.org/software/coreutils/manual/html_node/sha2-utilities.html) mevcut checksum doğrulaması sunar. [Python hashlib](https://docs.python.org/3/library/hashlib.html) standart SHA256 uygulamasını sağlar. Kanıt Kontrol bu temelleri mevcut JSON katalogları, bayt sayısı denetimi, Türkçe rapor ve taşınabilir beceriyle bir araya getirir.

## Lisans

MIT. Eklenti paketi bir sunucu veya MCP aracı eklemez. Hesaba kaydetme, GitHub yayını ve kamuya açık mağaza kabulü ayrı işlemlerdir; paket varlığı bir mağaza onayı iddiası değildir.
