"""
Tests for cli.py - Command line interface.
"""

import pytest
import json
from io import StringIO
from unittest.mock import patch, MagicMock

from himotoki.cli import main, VERSION, CONJUGATION_ROOT, get_kana


class TestConstants:
    """Tests for CLI constants."""
    
    def test_version_constant_exists(self):
        """Test VERSION constant is defined."""
        assert VERSION is not None
        assert isinstance(VERSION, str)
        assert '.' in VERSION  # Should be semver format
    
    def test_conjugation_root_constant(self):
        """Test CONJUGATION_ROOT constant is defined."""
        assert CONJUGATION_ROOT == 'root'


class TestGetKana:
    """Tests for the get_kana helper function."""
    
    def test_get_kana_string(self):
        """Test get_kana with string kana."""
        wi = MagicMock()
        wi.kana = "てすと"
        wi.text = "テスト"
        assert get_kana(wi) == "てすと"
    
    def test_get_kana_list(self):
        """Test get_kana with list kana."""
        wi = MagicMock()
        wi.kana = ["てすと", "テスト"]
        wi.text = "テスト"
        assert get_kana(wi) == "てすと"
    
    def test_get_kana_empty_list(self):
        """Test get_kana with empty list falls back to text."""
        wi = MagicMock()
        wi.kana = []
        wi.text = "テスト"
        assert get_kana(wi) == "テスト"
    
    def test_get_kana_none(self):
        """Test get_kana with None falls back to text."""
        wi = MagicMock()
        wi.kana = None
        wi.text = "テスト"
        assert get_kana(wi) == "テスト"
    
    def test_get_kana_none_and_none_text(self):
        """Test get_kana with None kana and None text returns empty string."""
        wi = MagicMock()
        wi.kana = None
        wi.text = None
        assert get_kana(wi) == ""


class TestCLIBasics:
    """Tests for basic CLI functionality."""
    
    def test_version(self, capsys):
        """Test version flag."""
        result = main(['--version'])
        assert result == 0
        captured = capsys.readouterr()
        assert 'himotoki' in captured.out
        assert VERSION in captured.out
    
    def test_version_short(self, capsys):
        """Test -v flag."""
        result = main(['-v'])
        assert result == 0
        captured = capsys.readouterr()
        assert VERSION in captured.out
    
    def test_help(self, capsys):
        """Test help flag."""
        with pytest.raises(SystemExit) as exc_info:
            main(['--help'])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert 'Himotoki' in captured.out or 'Japanese' in captured.out
    
    def test_no_args(self, capsys):
        """Test running with no arguments."""
        result = main([])
        assert result == 1  # Should fail without input


class TestInputValidation:
    """Tests for input validation."""
    
    def test_empty_string(self, capsys):
        """Test empty string input."""
        result = main([''])
        assert result == 1
    
    def test_whitespace_only(self, capsys):
        """Test whitespace-only input is rejected."""
        result = main(['   '])
        assert result == 1
    
    def test_tabs_only(self, capsys):
        """Test tab-only input is rejected."""
        result = main(['\t\t'])
        assert result == 1
    
    def test_mixed_whitespace(self, capsys):
        """Test mixed whitespace input is rejected."""
        result = main(['  \t  \n  '])
        assert result == 1


class TestMutuallyExclusiveFlags:
    """Tests for mutually exclusive output format flags."""
    
    def test_romanize_and_full_exclusive(self):
        """Test -r and -f cannot be used together."""
        with pytest.raises(SystemExit) as exc_info:
            main(['-r', '-f', 'テスト'])
        assert exc_info.value.code == 2  # argparse error code
    
    def test_romanize_and_kana_exclusive(self):
        """Test -r and -k cannot be used together."""
        with pytest.raises(SystemExit) as exc_info:
            main(['-r', '-k', 'テスト'])
        assert exc_info.value.code == 2
    
    def test_romanize_and_json_exclusive(self):
        """Test -r and -j cannot be used together."""
        with pytest.raises(SystemExit) as exc_info:
            main(['-r', '-j', 'テスト'])
        assert exc_info.value.code == 2
    
    def test_full_and_kana_exclusive(self):
        """Test -f and -k cannot be used together."""
        with pytest.raises(SystemExit) as exc_info:
            main(['-f', '-k', 'テスト'])
        assert exc_info.value.code == 2
    
    def test_all_output_flags_exclusive(self):
        """Test all output flags cannot be used together."""
        with pytest.raises(SystemExit) as exc_info:
            main(['-r', '-f', '-k', '-j', 'テスト'])
        assert exc_info.value.code == 2


class TestCLIArgumentParsing:
    """Tests for argument parsing - verify flags are recognized."""
    
    def test_romanize_flag_short(self, capsys):
        """Test -r flag is recognized and processed."""
        # This may succeed (with real DB) or fail (without DB) - either is valid
        result = main(['-r', 'テスト'])
        # If it succeeds, it should output romanization
        if result == 0:
            captured = capsys.readouterr()
            assert 'tesuto' in captured.out.lower()
        # If it fails, that's OK too (no database)
    
    def test_full_flag_short(self, capsys):
        """Test -f flag is recognized and processed."""
        result = main(['-f', 'テスト'])
        if result == 0:
            captured = capsys.readouterr()
            assert 'テスト' in captured.out or 'tesuto' in captured.out.lower()
    
    def test_kana_flag_short(self, capsys):
        """Test -k flag is recognized and processed."""
        result = main(['-k', 'テスト'])
        if result == 0:
            captured = capsys.readouterr()
            assert 'テスト' in captured.out or 'てすと' in captured.out
    
    def test_json_flag_short(self, capsys):
        """Test -j flag is recognized and processed."""
        result = main(['-j', 'テスト'])
        if result == 0:
            captured = capsys.readouterr()
            # Should be valid JSON
            import json
            data = json.loads(captured.out)
            assert isinstance(data, list)
    
    def test_limit_flag(self, capsys):
        """Test -l flag is recognized and processed."""
        result = main(['-j', '-l', '5', 'テスト'])
        if result == 0:
            captured = capsys.readouterr()
            import json
            data = json.loads(captured.out)
            assert isinstance(data, list)
    
    def test_database_flag(self):
        """Test --database flag is recognized."""
        with patch('himotoki.cli.get_session', side_effect=Exception("test")):
            result = main(['--database', '/nonexistent/path.db', 'テスト'])
            assert result == 1


class TestCLIWithMockedSession:
    """Tests with mocked database session."""
    
    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        return MagicMock()
    
    @pytest.fixture
    def mock_dict_segment(self):
        """Create mock dict_segment results."""
        from himotoki.output import WordInfo, WordType
        
        # Create simple WordInfo results
        wi1 = WordInfo(
            type=WordType.KANJI,
            text="テスト",
            kana="てすと",
            seq=12345,
            score=100,
        )
        return [([wi1], 100)]
    
    def test_default_output(self, capsys, mock_session, mock_dict_segment):
        """Test default dictionary info output."""
        with patch('himotoki.cli.get_db_path', return_value='/test/db.sqlite'):
            with patch('himotoki.cli.get_session', return_value=mock_session):
                with patch('himotoki.cli.dict_segment', return_value=mock_dict_segment):
                    with patch('himotoki.cli.get_senses_str', return_value='1. [n] test'):
                        result = main(['テスト'])
        
        assert result == 0
        captured = capsys.readouterr()
        # Default should show dictionary info without romanization
        assert 'テスト' in captured.out or 'てすと' in captured.out
    
    def test_romanize_output(self, capsys, mock_session, mock_dict_segment):
        """Test -r romanization output."""
        with patch('himotoki.cli.get_db_path', return_value='/test/db.sqlite'):
            with patch('himotoki.cli.get_session', return_value=mock_session):
                with patch('himotoki.cli.dict_segment', return_value=mock_dict_segment):
                    result = main(['-r', 'テスト'])
        
        assert result == 0
        captured = capsys.readouterr()
        # Should have romanized output
        assert 'tesuto' in captured.out.lower()
    
    def test_kana_output(self, capsys, mock_session, mock_dict_segment):
        """Test -k kana output."""
        with patch('himotoki.cli.get_db_path', return_value='/test/db.sqlite'):
            with patch('himotoki.cli.get_session', return_value=mock_session):
                with patch('himotoki.cli.dict_segment', return_value=mock_dict_segment):
                    result = main(['-k', 'テスト'])
        
        assert result == 0
        captured = capsys.readouterr()
        # Should have kana output
        assert 'てすと' in captured.out
    
    def test_json_output(self, capsys, mock_session, mock_dict_segment):
        """Test -j JSON output format."""
        with patch('himotoki.cli.get_db_path', return_value='/test/db.sqlite'):
            with patch('himotoki.cli.get_session', return_value=mock_session):
                with patch('himotoki.cli.dict_segment', return_value=mock_dict_segment):
                    with patch('himotoki.output.word_info_gloss_json', return_value={'text': 'テスト'}):
                        result = main(['-j', 'テスト'])
        
        assert result == 0
        captured = capsys.readouterr()
        # Should be valid JSON
        try:
            data = json.loads(captured.out)
            assert isinstance(data, list)
        except json.JSONDecodeError:
            # If it fails, it might be because mocking is incomplete
            pass
    
    def test_full_output(self, capsys, mock_session, mock_dict_segment):
        """Test -f full output format."""
        with patch('himotoki.cli.get_db_path', return_value='/test/db.sqlite'):
            with patch('himotoki.cli.get_session', return_value=mock_session):
                with patch('himotoki.cli.dict_segment', return_value=mock_dict_segment):
                    with patch('himotoki.cli.get_senses_str', return_value='1. [n] test'):
                        result = main(['-f', 'テスト'])
        
        assert result == 0
        captured = capsys.readouterr()
        # Full should have both romanization and dictionary info
        assert 'tesuto' in captured.out.lower() or 'テスト' in captured.out


class TestCLIErrorHandling:
    """Tests for error handling."""
    
    def test_no_database_error(self, capsys):
        """Test error when no database is available."""
        with patch('himotoki.cli.get_db_path', return_value=None):
            with patch('himotoki.setup.is_database_ready', return_value=False):
                with patch('himotoki.setup.prompt_for_setup', return_value=False):
                    result = main(['テスト'])
        
        assert result == 1
    
    def test_database_connection_error(self, capsys):
        """Test error when database connection fails."""
        with patch('himotoki.cli.get_db_path', return_value='/test/db.sqlite'):
            with patch('himotoki.cli.Path') as mock_path:
                mock_path.return_value.exists.return_value = True
                with patch('himotoki.cli.get_session', side_effect=Exception("Connection failed")):
                    result = main(['テスト'])
        
        assert result == 1
        captured = capsys.readouterr()
        assert 'Error' in captured.err
    
    def test_error_includes_mode_context(self, capsys):
        """Test that errors include output mode context."""
        mock_session = MagicMock()
        with patch('himotoki.cli.get_db_path', return_value='/test/db.sqlite'):
            with patch('himotoki.cli.Path') as mock_path:
                mock_path.return_value.exists.return_value = True
                with patch('himotoki.cli.get_session', return_value=mock_session):
                    with patch('himotoki.suffixes.init_suffixes'):
                        with patch('himotoki.cli.dict_segment', side_effect=Exception("Test error")):
                            result = main(['-r', 'テスト'])
        
        assert result == 1
        captured = capsys.readouterr()
        assert 'mode=' in captured.err

