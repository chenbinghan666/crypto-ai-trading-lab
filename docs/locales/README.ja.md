# Crypto AI Trading Lab

[简体中文](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/README.md) · [English](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.en.md) · **日本語** · [Deutsch](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.de.md) · [Français](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.fr.md) · [Español](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.es.md) · [Português](https://github.com/chenbinghan666/crypto-ai-trading-lab/blob/main/docs/locales/README.pt.md)

バックテスト、FreqAI のモデル実験、先物取引のシミュレーションをまとめた中国語の作業環境です。ルールベースとモデルベースの戦略を個別の仮想台帳で比較できます。用途は研究とシミュレーションです。

Python · Freqtrade · FreqAI

中国語の Web 管理ページを提供し、Freqtrade / FreqUI、FreqAI CPU LightGBM、TradingAgents / DeepSeek を統合した、独立した仮想通貨調査および契約シミュレーション システムです。ランタイムは Codex やチャット セッションに依存しません。

**は現在、リサーチと仮想取引のみをサポートしており、実際の取引は禁止されています。戦略もモデルも、実証済みの収益性を示すものではありません。**

## 機能

- Binance の公開相場、接続診断、K ライン、更新カウントダウン。 Gate の永久公開見積は、独立した契約のシミュレーションに使用されます。
- Binance U ベースの契約アカウントは、資産とポジションのクエリに読み取り専用でバインドされています。 API 設定は暗号化され、ローカルに保存されます。
- TradingAgents / DeepSeek の調査タスク、API 使用量の計算、予算の予約および料金制限。
- FreqAI CPU トレーニング、時間分離評価、モデルの保存、リロード検証。
- 公式 Freqtrade 契約バックテストとリアルタイムの予行演習: ロングポジションとショートポジション、注文の開始と終了、取引ステータスと損益。
- 自動最適化: 候補の生成、トレーニング、コストのサンプル外比較、ショート後のポジションを通じてシミュレーションのバージョンを切り替え、パフォーマンスが低下した場合はロールバックします。
- 15m AI制御実験：ルールグループとFreqAIモデルグループは、独立した仮想台帳を使用してシグナル、取引記録、損益を比較します。
- 独立したプロセス デーモン、切断再接続、状態回復、重複排除の順序、Windows のワンクリック開始と停止、および Docker Compose 構成。

## Windowsが起動します

環境の準備と依存関係のインストールについては、[Windows のインストール](../../docs/INSTALL_WINDOWS.md) および [の展開手順](../../docs/DEPLOYMENT.md) を参照してください。 WSL/Ubuntu および互換性のある Python 環境が必要です。 Windows スクリプトはプロジェクト パスを検出します。

1. リポジトリのクローンを作成し、インストール ドキュメントに従って WSL と依存関係を準備します。
2. `启动系统.cmd` をダブルクリックして <http://127.0.0.1:8080> にアクセスします。
3. `FreqUI登录信息.cmd` をダブルクリックしてローカル管理パスワードを表示し、Web ページ上のパネルのロックを解除します。
4. Web 上で必要な API を構成し、価格とサービスを確認し、調査、トレーニング、またはシミュレーションを手動で有効にします。
5. サービスを停止するには `停止系统.cmd` をダブルクリックし、実行ステータスを表示するには `查看状态.cmd` をダブルクリックします。

ブラウザや開発ツールを閉じても、バックグラウンド サービスには影響しません。コンピュータをシャットダウンまたは休止状態にすると、ローカル操作が中断されます。新しい展開では、デフォルトではシミュレーションと自動最適化が開始されません。ウェアハウスには開発者の構成、キー、モデル、実行データは含まれていないため、クローン作成後にウェアハウス自体を初期化する必要があります。

公式リサーチ FreqUI: <http://127.0.0.1:8081>。元の 1 時間のシミュレーション開始後の読み取り専用 FreqUI: <http://127.0.0.1:8083>。

## Docker Compose

```sh
docker compose up -d --build
docker compose down
```

デフォルトのポートはローカル マシンにのみバインドされます。最初の展開では、資格情報とモジュール スイッチを自分で構成する必要があります。メインのプログラムとリサーチ サービスのイメージ構成が提供されています。実際の Docker ビルドと Linux VPS デプロイメントはターゲット環境で受け入れられる必要があります。

## シミュレーションとAIの境界

取引所取引許可なしで仮想資金の使用をシミュレートします。現在のレバレッジは 1 倍に固定されており、独立したポジション、毎日の損失、ドローダウン、および連続損失の冷却制限は維持されます。戦略は終了 K ラインに基づいて評価されます。シグナルがない場合、またはリスク管理が解除されていない場合は、ゼロ取引が許可されます。

15 メートル制御実験の AI は、ローカル FreqAI LightGBM 予測フィルタリングを指します。 TradingAgents / DeepSeek は、別個の調査および最適化プロセスです。実験モデルは営利目的では受け入れられておらず、実験結果は元のアカウント戦略に直接置き換わるものではありません。自動最適化は、制限されたパラメーターとモデルを調整するだけであり、AI によって生成された任意のコードは実行されません。

手数料、スリッページ手数料換算、資本手数料、トレーニングデータの分離、最終検査ルールについては関連文書を参照してください。コスト換算では実際の取引への影響を完全に表すことはできず、短期的なシミュレートされた収益は戦略の有効性を証明できません。

## 認証情報と運用データ

API キーはローカル Web ページでのみ入力し、GitHub、Issue、またはチャットに送信しないでください。読み取り専用の Binance アカウント権限を使用します。このアカウントでは取引は実行されません。 DeepSeek 通話には、予算と価格検証の有効性が適用されます。

ネイティブ環境ファイル、キー、データベース、モデル、ログ、実行レポート、およびスクリーンショットは、`.gitignore` によって除外されます。パブリック リポジトリには、ソース コード、構成テンプレート、テスト、ドキュメントのみが含まれます。プログラムの実行後に生成されたレポートはローカル マシンに残ります。

## ドキュメント

- [導入と障害回復](../../docs/DEPLOYMENT.md) · [回復ガイド](../../docs/RECOVERY.md)
- [Web ページ操作](../../docs/WEB_CONTROLS.md) · [アカウント読み取り専用バインディング](../../docs/BINANCE_ACCOUNT.md)
- [契約シミュレーション](../../docs/PAPER_TRADING.md)・[15m AI制御実験](../../docs/FAST_AI_EXPERIMENT.md)
- [FreqAI CPU](../../docs/FREQAI_CPU.md) · [AI 研究](../../docs/AI_RESEARCH.md)
- [は](../../docs/AUTOMATIC_OPTIMIZATION.md) ・ [リスク ポリシー](../../docs/RISK_POLICY.md) を自動的に最適化します
- [単独運転受付](../../docs/INDEPENDENCE_ACCEPTANCE.md)

## 開発検証

```powershell
.\scripts\lab.ps1 test
```

最初に、ドキュメントで指定されている実行中の依存関係をインストールする必要があります。ネットワーク受け入れ、独立したバックグラウンド回復、実験的サービス受け入れスクリプトは `scripts/` にあります。一部のスクリプトでは、ローカル サービスが開始されている必要があります。受入出力は倉庫とともにリリースされません。

プロジェクトで使用されるアップストリームには、[Freqtrade](https://github.com/freqtrade/freqtrade) および [TradingAgents](https://github.com/TauricResearch/TradingAgents) が含まれます。依存関係のバージョンは要件ロック ファイルで修正され、アップストリーム ソフトウェアはそれぞれのライセンスに従います。
